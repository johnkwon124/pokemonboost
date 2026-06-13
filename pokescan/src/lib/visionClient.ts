/**
 * Browser-side Cloud Vision OCR.
 * Uses a public API key restricted by HTTP referrer in the Google Cloud console,
 * so it is safe(ish) to ship in client code — the key only works from our origin.
 */

const KEY = process.env.NEXT_PUBLIC_GOOGLE_VISION_API_KEY;

interface VisionResponse {
  responses?: {
    fullTextAnnotation?: { text?: string };
    textAnnotations?: { description?: string }[];
    error?: { message?: string };
  }[];
}

export async function runVisionOcr(imageBase64: string): Promise<string> {
  if (!KEY) throw new Error("NEXT_PUBLIC_GOOGLE_VISION_API_KEY 가 설정되지 않았습니다");

  const res = await fetch(`https://vision.googleapis.com/v1/images:annotate?key=${KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      requests: [
        {
          image: { content: imageBase64 },
          features: [{ type: "TEXT_DETECTION", maxResults: 1 }]
        }
      ]
    })
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    if (res.status === 403 && /referer|referrer|API_KEY_HTTP/i.test(detail)) {
      throw new Error(
        "이 사이트 주소가 Vision API 키에 등록되지 않았어요. Google Cloud 콘솔에서 이 도메인을 HTTP 리퍼러에 추가하세요."
      );
    }
    throw new Error(`Vision API ${res.status}: ${detail.slice(0, 160)}`);
  }

  const json = (await res.json()) as VisionResponse;
  const first = json.responses?.[0];
  if (first?.error?.message) throw new Error(first.error.message);
  return first?.fullTextAnnotation?.text ?? first?.textAnnotations?.[0]?.description ?? "";
}
