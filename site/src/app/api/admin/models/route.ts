import { NextResponse } from "next/server";

// Model definitions with provider info
const LLM_MODELS = [
  {
    id: "huggingface/Qwen/Qwen2.5-72B-Instruct",
    label: "Qwen 2.5 72B (Hugging Face)",
    provider: "huggingface",
    free: false,
  },
  {
    id: "huggingface/Qwen/Qwen2.5-Coder-32B-Instruct",
    label: "Qwen 2.5 Coder 32B (Hugging Face)",
    provider: "huggingface",
    free: false,
  },
  {
    id: "openai/gpt-4o",
    label: "GPT-4o",
    provider: "openai",
    free: false,
  },
  {
    id: "openai/gpt-4o-mini",
    label: "GPT-4o Mini",
    provider: "openai",
    free: false,
  },
  {
    id: "anthropic/claude-sonnet-4-20250514",
    label: "Claude Sonnet 4",
    provider: "anthropic",
    free: false,
  },
  {
    id: "anthropic/claude-haiku-4-20250514",
    label: "Claude Haiku 4",
    provider: "anthropic",
    free: false,
  },
];

const VIDEO_MODELS = [
  {
    id: "huggingface/tencent/HunyuanVideo",
    label: "HunyuanVideo (Hugging Face)",
    provider: "huggingface",
    free: false,
  },
  {
    id: "huggingface/THUDM/CogVideoX-5b",
    label: "CogVideoX 5B (Hugging Face)",
    provider: "huggingface",
    free: false,
  },
  {
    id: "huggingface/ByteDance/AnimateDiff-Lightning",
    label: "AnimateDiff Lightning (Local GPU)",
    provider: "huggingface",
    free: false,
  },
  {
    id: "byteplus/seedance2.0",
    label: "Seedance 2.0 (BytePlus)",
    provider: "byteplus",
    free: false,
  },
];

const AUDIO_MODELS = [
  {
    id: "huggingface/facebook/musicgen-medium",
    label: "MusicGen Medium (Hugging Face)",
    provider: "huggingface",
    free: false,
  },
  {
    id: "huggingface/suno/bark",
    label: "Bark TTS (Hugging Face)",
    provider: "huggingface",
    free: false,
  },
];

function checkKeyAvailable(provider: string): boolean {
  switch (provider) {
    case "openai":
      return !!process.env.OPENAI_API_KEY && process.env.OPENAI_API_KEY !== "sk-your_key_here";
    case "anthropic":
      return !!process.env.ANTHROPIC_API_KEY && process.env.ANTHROPIC_API_KEY !== "sk-ant-your_key_here";
    case "huggingface":
      return !!process.env.HUGGINGFACE_API_TOKEN && process.env.HUGGINGFACE_API_TOKEN !== "hf-your_token_here";
    case "atlascloud":
      return !!process.env.ATLASCLOUD_API_KEY && process.env.ATLASCLOUD_API_KEY !== "your_key_here";
    case "byteplus":
      return !!process.env.ARK_API_KEY && process.env.ARK_API_KEY !== "your_key_here";
    default:
      return false;
  }
}

export async function GET() {
  const enrich = (models: typeof LLM_MODELS) =>
    models.map((m) => ({
      ...m,
      available: m.free || checkKeyAvailable(m.provider),
    }));

  return NextResponse.json({
    llm: enrich(LLM_MODELS),
    video: enrich(VIDEO_MODELS),
    audio: enrich(AUDIO_MODELS),
  });
}
