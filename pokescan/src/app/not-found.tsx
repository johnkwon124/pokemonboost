import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-sm text-ink-300">페이지를 찾을 수 없어요</p>
      <Link href="/" className="rounded-full bg-accent px-4 py-2 text-xs font-semibold text-ink-950">
        스캔으로 돌아가기
      </Link>
    </div>
  );
}
