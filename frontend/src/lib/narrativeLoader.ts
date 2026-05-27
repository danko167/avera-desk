import type { LoaderMessage } from "@danko167/narrative-loader";

export const REQUEST_PROCESSING_MESSAGES: LoaderMessage[] = [
  { text: "Parsing what you said", emoji: "🧠", animation: "dots" },
  { text: "Matching an action", emoji: "🧭", animation: "dots" },
  { text: "Preparing your request", emoji: "⚙️", animation: "dots" },
  { text: "Finalizing response", emoji: "✨", animation: "dots" },
];

export const RESPONSE_PROCESSING_MESSAGES: LoaderMessage[] = [
  { text: "Reviewing your response", emoji: "📝", animation: "dots" },
  { text: "Applying your action", emoji: "🛠️", animation: "dots" },
  { text: "Updating context", emoji: "🔄", animation: "dots" },
  { text: "Wrapping this up", emoji: "✅", animation: "dots" },
];