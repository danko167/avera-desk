import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Group, Loader, Stack, Tooltip } from "@mantine/core";
import { IconMicrophone } from "@tabler/icons-react";
import { listen } from "@tauri-apps/api/event";
import { createLogger } from "../lib/logger";

export type ListenPhase = "idle" | "starting" | "listening" | "stopping";

type AudioInputProps = {
  onAudioChunk?: (chunk: { audioBase64: string; bytes: number }) => void;
  onListenStateChange?: (active: boolean, phase: ListenPhase) => void;
  onCloudSessionChange?: (active: boolean) => void;
  disabled?: boolean;
};

const MIC_RELEASE_LOADER_MS = 2900;
const logger = createLogger("AudioInput");

export function AudioInput({ onAudioChunk, onListenStateChange, onCloudSessionChange, disabled = false }: AudioInputProps) {
  const [isListening, setIsListening] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const monitorSinkRef = useRef<GainNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const pendingPcmBytesRef = useRef<Uint8Array[]>([]);
  const pendingPcmByteCountRef = useRef(0);
  const pcmFlushTimeoutRef = useRef<number | null>(null);
  const pushToTalkHeldRef = useRef(false);
  const pttMouseStartTimeoutRef = useRef<number | null>(null);
  const cloudSessionActiveRef = useRef(false);
  const sessionRef = useRef(0);
  const workletModuleLoadedRef = useRef(false);
  const scriptProcessorFallbackRef = useRef(false);
  const stopLoaderTimeoutRef = useRef<number | null>(null);

  const clearMouseStartTimeout = useCallback(() => {
    if (pttMouseStartTimeoutRef.current !== null) {
      window.clearTimeout(pttMouseStartTimeoutRef.current);
      pttMouseStartTimeoutRef.current = null;
    }
  }, []);

  const clearStopLoaderTimeout = useCallback(() => {
    if (stopLoaderTimeoutRef.current !== null) {
      window.clearTimeout(stopLoaderTimeoutRef.current);
      stopLoaderTimeoutRef.current = null;
    }
  }, []);

  const releaseMicTracks = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  const closeMicStream = useCallback((options?: { hard?: boolean }) => {
    const hard = options?.hard === true;

    if (pcmFlushTimeoutRef.current !== null) {
      window.clearTimeout(pcmFlushTimeoutRef.current);
      pcmFlushTimeoutRef.current = null;
    }

    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }

    releaseMicTracks();

    if (hard) {
      if (monitorSinkRef.current) {
        monitorSinkRef.current.disconnect();
        monitorSinkRef.current = null;
      }

      if (workletNodeRef.current) {
        workletNodeRef.current.port.onmessage = null;
        workletNodeRef.current.disconnect();
        workletNodeRef.current = null;
      }

      if (scriptProcessorRef.current) {
        scriptProcessorRef.current.onaudioprocess = null;
        scriptProcessorRef.current.disconnect();
        scriptProcessorRef.current = null;
      }

      if (audioContextRef.current) {
        void audioContextRef.current.close();
        audioContextRef.current = null;
      }

      workletModuleLoadedRef.current = false;
      scriptProcessorFallbackRef.current = false;
    }

    cloudSessionActiveRef.current = false;
  }, [releaseMicTracks]);

  const bytesToBase64 = (bytes: Uint8Array) => {
    let binary = "";
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  };

  const flushPendingPcm = useCallback(() => {
    if (pendingPcmByteCountRef.current === 0) {
      return;
    }

    const merged = new Uint8Array(pendingPcmByteCountRef.current);
    let offset = 0;
    for (const chunk of pendingPcmBytesRef.current) {
      merged.set(chunk, offset);
      offset += chunk.byteLength;
    }

    pendingPcmBytesRef.current = [];
    pendingPcmByteCountRef.current = 0;

    const audioBase64 = bytesToBase64(merged);
    onAudioChunk?.({ audioBase64, bytes: merged.byteLength });
  }, [onAudioChunk]);

  const enqueueCloudPcmBytes = useCallback((pcmBytes: Uint8Array) => {
    if (pcmBytes.byteLength === 0) {
      return;
    }

    pendingPcmBytesRef.current.push(pcmBytes);
    pendingPcmByteCountRef.current += pcmBytes.byteLength;

    if (pendingPcmByteCountRef.current >= 4096) {
      if (pcmFlushTimeoutRef.current !== null) {
        window.clearTimeout(pcmFlushTimeoutRef.current);
        pcmFlushTimeoutRef.current = null;
      }
      flushPendingPcm();
      return;
    }

    if (pcmFlushTimeoutRef.current === null) {
      pcmFlushTimeoutRef.current = window.setTimeout(() => {
        pcmFlushTimeoutRef.current = null;
        flushPendingPcm();
      }, 100);
    }
  }, [flushPendingPcm]);

  const stopCloudSession = useCallback((options?: { deferFlush?: boolean; force?: boolean }) => {
    if (!options?.force && !cloudSessionActiveRef.current) {
      return;
    }

    const finalizeStop = () => {
      cloudSessionActiveRef.current = false;
      onCloudSessionChange?.(false);
    };

    if (options?.deferFlush === true) {
      window.setTimeout(() => {
        flushPendingPcm();
        finalizeStop();
      }, 0);
    } else {
      flushPendingPcm();
      finalizeStop();
    }
  }, [flushPendingPcm, onCloudSessionChange]);

  const startCloudSession = useCallback(() => {
    if (cloudSessionActiveRef.current) {
      return;
    }

    cloudSessionActiveRef.current = true;
    onCloudSessionChange?.(true);
  }, [onCloudSessionChange]);

  const handlePcmBytes = useCallback((pcmBytes: Uint8Array) => {
    if (pcmBytes.byteLength === 0) {
      return;
    }
    enqueueCloudPcmBytes(pcmBytes);
  }, [enqueueCloudPcmBytes]);

  const setupPcmStreaming = useCallback(async (stream: MediaStream) => {
    let audioContext = audioContextRef.current;
    if (!audioContext) {
      audioContext = new AudioContext({ sampleRate: 24000, latencyHint: "interactive" });
      audioContextRef.current = audioContext;
    }

    let monitorSink = monitorSinkRef.current;
    if (!monitorSink) {
      monitorSink = audioContext.createGain();
      monitorSink.gain.value = 0;
      monitorSink.connect(audioContext.destination);
      monitorSinkRef.current = monitorSink;
    }

    const sourceNode = audioContext.createMediaStreamSource(stream);
    sourceNodeRef.current = sourceNode;

    const emitChunkFromFloat = (input: Float32Array) => {
      if (!input || input.length === 0) {
        return;
      }

      const pcm16 = new Int16Array(input.length);
      for (let i = 0; i < input.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, input[i]));
        pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }

      const pcmBytes = new Uint8Array(pcm16.buffer);
      handlePcmBytes(pcmBytes);
    };

    try {
      if (!scriptProcessorFallbackRef.current) {
        if (!workletModuleLoadedRef.current) {
          await audioContext.audioWorklet.addModule("/pcm16-worklet.js");
          workletModuleLoadedRef.current = true;
        }

        if (!workletNodeRef.current) {
          const workletNode = new AudioWorkletNode(audioContext, "pcm16-processor", {
            numberOfInputs: 1,
            numberOfOutputs: 1,
            outputChannelCount: [1],
          });
          workletNode.connect(monitorSink);
          workletNodeRef.current = workletNode;
        }

        workletNodeRef.current.port.onmessage = (event) => {
          const pcmBuffer = event.data;
          if (!(pcmBuffer instanceof ArrayBuffer) || pcmBuffer.byteLength === 0) {
            return;
          }

          const pcmBytes = new Uint8Array(pcmBuffer);
          handlePcmBytes(pcmBytes);
        };

        sourceNode.connect(workletNodeRef.current);
      } else {
        throw new Error("ScriptProcessor fallback enabled");
      }
    } catch (error) {
      if (!scriptProcessorFallbackRef.current) {
        logger.warn("AudioWorklet unavailable; falling back to ScriptProcessorNode.", error);
      }
      scriptProcessorFallbackRef.current = true;
      if (!scriptProcessorRef.current) {
        const scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);
        scriptProcessor.connect(monitorSink);
        scriptProcessorRef.current = scriptProcessor;
      }
      scriptProcessorRef.current.onaudioprocess = (event) => {
        emitChunkFromFloat(event.inputBuffer.getChannelData(0));
      };

      sourceNode.connect(scriptProcessorRef.current);
    }

    if (audioContext.state !== "running") {
      await audioContext.resume();
    }
  }, [handlePcmBytes]);

  const ensureStream = useCallback(async () => {
    if (streamRef.current && streamRef.current.active) {
      return streamRef.current;
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    streamRef.current = stream;
    return stream;
  }, []);

  const prewarmAudioEngine = useCallback(async () => {
    let audioContext = audioContextRef.current;
    if (!audioContext) {
      audioContext = new AudioContext({ sampleRate: 24000, latencyHint: "interactive" });
      audioContextRef.current = audioContext;
    }

    if (!monitorSinkRef.current) {
      const monitorSink = audioContext.createGain();
      monitorSink.gain.value = 0;
      monitorSink.connect(audioContext.destination);
      monitorSinkRef.current = monitorSink;
    }

    if (!scriptProcessorFallbackRef.current && !workletModuleLoadedRef.current) {
      try {
        await audioContext.audioWorklet.addModule("/pcm16-worklet.js");
        workletModuleLoadedRef.current = true;
      } catch (error) {
        logger.warn("Audio worklet prewarm failed.", error);
      }
    }
  }, []);

  const startListening = useCallback(async () => {
    if (disabled || isListening || isStarting) {
      return;
    }

    const sessionId = ++sessionRef.current;

    // Update UI immediately so recording feels responsive.
    clearStopLoaderTimeout();
    setIsStopping(false);
    setIsStarting(true);
    setIsListening(true);
    onListenStateChange?.(true, "starting");

    try {
      const stream = await ensureStream();

      // If stop was requested while waiting for getUserMedia, abort startup.
      if (sessionId !== sessionRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        if (streamRef.current === stream) {
          streamRef.current = null;
        }
        return;
      }

      await setupPcmStreaming(stream);

      if (sessionId !== sessionRef.current) {
        closeMicStream();
        return;
      }

      startCloudSession();
      onListenStateChange?.(true, "listening");
    } catch (error) {
      logger.error("Microphone access denied.", error);
      setIsListening(false);
      setIsStopping(false);
      onListenStateChange?.(false, "idle");
      closeMicStream();
      alert("Microphone access denied. Check permissions.");
    } finally {
      if (sessionId === sessionRef.current) {
        setIsStarting(false);
      }
    }
  }, [
    closeMicStream,
    ensureStream,
    isListening,
    isStarting,
    onListenStateChange,
    setupPcmStreaming,
    startCloudSession,
    disabled,
  ]);

  const stopListening = useCallback(() => {
    // Invalidate any in-flight async startListening call.
    sessionRef.current += 1;
    const hadCloudSession = cloudSessionActiveRef.current;

    // Stop the OS mic indicator as quickly as possible.
    releaseMicTracks();
    clearMouseStartTimeout();

    pushToTalkHeldRef.current = false;
    setIsListening(false);
    setIsStarting(false);
    setIsStopping(true);
    onListenStateChange?.(false, "stopping");

    clearStopLoaderTimeout();
    stopLoaderTimeoutRef.current = window.setTimeout(() => {
      setIsStopping(false);
      stopLoaderTimeoutRef.current = null;
    }, MIC_RELEASE_LOADER_MS);

    closeMicStream();

    window.setTimeout(() => {
      if (hadCloudSession) {
        stopCloudSession({ deferFlush: true, force: true });
      }
    }, 0);
  }, [clearMouseStartTimeout, closeMicStream, onListenStateChange, releaseMicTracks, stopCloudSession]);

  useEffect(() => {
    void prewarmAudioEngine();
  }, [prewarmAudioEngine]);

  // Stable refs so global hotkey listeners (registered once) always see current state/callbacks.
  const isListeningRef = useRef(isListening);
  const isStartingRef = useRef(isStarting);
  const isDisabledRef = useRef(disabled);
  const startListeningRef = useRef(startListening);
  const stopListeningRef = useRef(stopListening);
  useEffect(() => { isListeningRef.current = isListening; }, [isListening]);
  useEffect(() => { isStartingRef.current = isStarting; }, [isStarting]);
  useEffect(() => { isDisabledRef.current = disabled; }, [disabled]);
  useEffect(() => { startListeningRef.current = startListening; }, [startListening]);
  useEffect(() => { stopListeningRef.current = stopListening; }, [stopListening]);

  useEffect(() => {
    if (disabled && isListeningRef.current) {
      stopListeningRef.current();
    }
  }, [disabled]);

  const isEditableTarget = (target: EventTarget | null) => {
    if (!(target instanceof HTMLElement)) {
      return false;
    }

    const tag = target.tagName.toLowerCase();
    return (
      tag === "input" ||
      tag === "textarea" ||
      target.isContentEditable
    );
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) {
        return;
      }

      // Hold Space for walkie-talkie style push-to-talk.
      if (
        event.code === "Space" &&
        !event.repeat &&
        !event.altKey &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.shiftKey &&
        !disabled &&
        !isListening &&
        !isStarting
      ) {
        event.preventDefault();
        pushToTalkHeldRef.current = true;
        void startListening();
      }
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      // Release Space to stop walkie-talkie recording.
      if (
        event.code === "Space" &&
        pushToTalkHeldRef.current &&
        isListening
      ) {
        event.preventDefault();
        stopListening();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [disabled, isListening, isStarting, startListening, stopListening]);

  // Listen for global hotkey events emitted by the Tauri Rust side.
  // These fire regardless of which app window has focus.
  useEffect(() => {
    const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
    if (!isTauri) return;

    // Register each listener and capture the Promise<unlisten>.
    // Cleanup calls .then(fn => fn()) so the unlisten is always invoked even if
    // the Promise hasn't resolved yet when the effect tears down.
    const pttStartPromise = listen("global-ptt-start", () => {
      if (!isDisabledRef.current && !pushToTalkHeldRef.current && !isListeningRef.current && !isStartingRef.current) {
        pushToTalkHeldRef.current = true;
        void startListeningRef.current();
      }
    });

    const pttStopPromise = listen("global-ptt-stop", () => {
      if (pushToTalkHeldRef.current && isListeningRef.current) {
        stopListeningRef.current();
      }
    });

    return () => {
      pttStartPromise.then((fn) => fn());
      pttStopPromise.then((fn) => fn());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Register once — state is accessed via refs above

  useEffect(() => {
    return () => {
      clearMouseStartTimeout();
      clearStopLoaderTimeout();
      stopCloudSession();
      closeMicStream({ hard: true });
    };
  }, [clearMouseStartTimeout, clearStopLoaderTimeout, closeMicStream, stopCloudSession]);

  return (
    <Stack gap={4}>
      <Group justify="center">
        <Tooltip label="Hold Space or hold this button for push-to-talk. Ctrl+Space when the app is not in focus.">
          <Button
            size="xs"
            variant={isListening ? "filled" : "light"}
            color={isStopping ? "yellow" : isListening ? "red" : "gray"}
            leftSection={
              isStarting || isStopping ? <Loader size={14} color="currentColor" /> : <IconMicrophone size={14} />
            }
            onMouseDown={() => {
              if (disabled) {
                return;
              }
              pushToTalkHeldRef.current = true;
              clearMouseStartTimeout();
              if (
                pushToTalkHeldRef.current &&
                !isListeningRef.current &&
                !isStartingRef.current
              ) {
                void startListeningRef.current();
              }
            }}
            onMouseUp={() => {
              clearMouseStartTimeout();
              if (isListeningRef.current) {
                stopListeningRef.current();
                return;
              }
              pushToTalkHeldRef.current = false;
            }}
            onMouseLeave={() => {
              clearMouseStartTimeout();
              if (isListeningRef.current) {
                stopListeningRef.current();
                return;
              }
              pushToTalkHeldRef.current = false;
            }}
            disabled={disabled || isStopping}
          >
            {isStarting ? "Activating..." : isStopping ? "Processing..." : isListening ? "Listening" : "Speak"}
          </Button>
        </Tooltip>
      </Group>
    </Stack>
  );
}
