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
    localSupported: true,
  },
  {
    id: "huggingface/THUDM/CogVideoX-5b",
    label: "CogVideoX 5B (Hugging Face)",
    provider: "huggingface",
    free: false,
    localSupported: true,
  },
  {
    id: "huggingface/Wan-AI/Wan2.1-T2V-14B",
    label: "Wan 2.1 T2V 14B (Hugging Face)",
    provider: "huggingface",
    free: false,
    localSupported: true,
  },
  {
    id: "huggingface/ByteDance/AnimateDiff-Lightning",
    label: "AnimateDiff Lightning (Local GPU)",
    provider: "huggingface",
    free: true,
    localSupported: true,
  },
  {
    id: "huggingface/ali-vilab/text-to-video-ms-1.7b",
    label: "Text-to-Video 1.7B (ModelScope)",
    provider: "huggingface",
    free: false,
    localSupported: true,
  },
  {
    id: "byteplus/seedance2.0",
    label: "Seedance 2.0 (BytePlus)",
    provider: "byteplus",
    free: false,
    localSupported: false,
  },
  {
    id: "laozhang/seedance2.0",
    label: "Seedance 2.0 (LaoZhang)",
    provider: "laozhang",
    free: false,
    localSupported: false,
  },
];

const IMAGE_MODELS = [
  {
    id: "laozhang/seedream-5-0-260128",
    label: "Seedream 5.0 (LaoZhang) [Default]",
    provider: "laozhang",
    free: false,
  },
  {
    id: "laozhang/seedream-4-5-251128",
    label: "Seedream 4.5 (LaoZhang)",
    provider: "laozhang",
    free: false,
  },
  {
    id: "laozhang/seedream-4-0-250828",
    label: "Seedream 4.0 (LaoZhang)",
    provider: "laozhang",
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
    case "laozhang":
      return !!process.env.LAOZHANG_API_KEY && process.env.LAOZHANG_API_KEY !== "sk-your_key_here";
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

  const enrichVideo = (models: typeof VIDEO_MODELS) =>
    models.map((m) => ({
      ...m,
      available: m.free || checkKeyAvailable(m.provider),
    }));

  return NextResponse.json({
    llm: enrich(LLM_MODELS),
    video: enrichVideo(VIDEO_MODELS),
    image: enrich(IMAGE_MODELS),
    audio: enrich(AUDIO_MODELS),
  });
}
