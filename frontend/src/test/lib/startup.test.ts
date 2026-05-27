import {
  APP_SETTINGS_STORAGE_KEY,
  APP_SETTINGS_SYNC_KEY,
  DEFAULT_APP_SETTINGS,
  readSettingsFromStorage,
  writeSettingsToStorage,
} from "../../lib/startup";

describe("startup storage helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("starts with whisper-1 as the default speech model", () => {
    expect(DEFAULT_APP_SETTINGS.speech_model).toBe("whisper-1");
  });

  it("reads connection settings from storage and merges defaults", () => {
    window.localStorage.setItem(
      APP_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        app_api_base_url: "  http://127.0.0.1:8000  ",
        app_ws_url: " ws://127.0.0.1:8000/ws ",
      }),
    );

    const parsed = readSettingsFromStorage();

    expect(parsed).not.toBeNull();
    expect(parsed).toEqual({
      ...DEFAULT_APP_SETTINGS,
      app_api_base_url: "http://127.0.0.1:8000",
      app_ws_url: "ws://127.0.0.1:8000/ws",
    });
  });

  it("returns null when stored settings are invalid JSON", () => {
    window.localStorage.setItem(APP_SETTINGS_STORAGE_KEY, "not-json");

    expect(readSettingsFromStorage()).toBeNull();
  });

  it("writes only connection settings and broadcasts when requested", () => {
    writeSettingsToStorage(
      {
        ...DEFAULT_APP_SETTINGS,
        app_api_base_url: "http://localhost:8000",
        app_ws_url: "ws://localhost:8000/ws",
        enable_text_input_mode: true,
      },
      { broadcast: true },
    );

    const savedRaw = window.localStorage.getItem(APP_SETTINGS_STORAGE_KEY);
    expect(savedRaw).not.toBeNull();
    expect(JSON.parse(savedRaw ?? "{}")).toEqual({
      app_api_base_url: "http://localhost:8000",
      app_ws_url: "ws://localhost:8000/ws",
    });

    const syncMarker = window.localStorage.getItem(APP_SETTINGS_SYNC_KEY);
    expect(syncMarker).not.toBeNull();
    expect(Number.isNaN(Number(syncMarker))).toBe(false);
  });
});