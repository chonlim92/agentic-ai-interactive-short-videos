"use client";

import { useState, useCallback, useEffect } from "react";
import { useLocale } from "@/lib/useLocale";

interface Props {
  urls: string[];
  /** "vertical" = 9:16, "horizontal" = 16:9 */
  orientation?: "vertical" | "horizontal";
}

export function GalleryGrid({ urls, orientation = "vertical" }: Props) {
  const locale = useLocale();
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const aspectClass = orientation === "vertical" ? "aspect-[9/16]" : "aspect-video";

  const openLightbox = (i: number) => setLightboxIndex(i);
  const closeLightbox = () => setLightboxIndex(null);

  const goPrev = useCallback(() => {
    setLightboxIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  const goNext = useCallback(() => {
    setLightboxIndex((prev) =>
      prev !== null && prev < urls.length - 1 ? prev + 1 : prev
    );
  }, [urls.length]);

  useEffect(() => {
    if (lightboxIndex === null) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeLightbox();
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [lightboxIndex, goPrev, goNext]);

  const handleDownload = (url: string, index: number) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = `scene_${index + 1}.png`;
    a.click();
  };

  return (
    <>
      <div className={`grid ${orientation === "vertical" ? "grid-cols-3 md:grid-cols-4 lg:grid-cols-6" : "grid-cols-2 md:grid-cols-3"} gap-3`}>
        {urls.map((url, i) => (
          <div
            key={i}
            className={`${aspectClass} rounded-xl overflow-hidden border border-white/[0.06] bg-black/20 relative group cursor-pointer`}
            onClick={() => openLightbox(i)}
          >
            <img
              src={url}
              alt={`${locale === "zh" ? "场景" : "Scene"} ${i + 1}`}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
            {/* Hover overlay */}
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors duration-200 flex items-center justify-center opacity-0 group-hover:opacity-100">
              <svg viewBox="0 0 24 24" className="w-8 h-8 text-white/80" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607zM10.5 7.5v6m3-3h-6" />
              </svg>
            </div>
          </div>
        ))}
      </div>

      {/* Lightbox Modal */}
      {lightboxIndex !== null && (
        <div
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={closeLightbox}
        >
          {/* Close button */}
          <button
            onClick={closeLightbox}
            className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center hover:bg-white/20 transition-colors z-10"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          {/* Download button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDownload(urls[lightboxIndex], lightboxIndex);
            }}
            className="absolute top-4 right-16 w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center hover:bg-white/20 transition-colors z-10"
            title={locale === "zh" ? "下载" : "Download"}
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          </button>

          {/* Counter */}
          <div className="absolute top-4 left-4 text-white/60 text-sm font-medium bg-black/40 px-3 py-1.5 rounded-full">
            {lightboxIndex + 1} / {urls.length}
          </div>

          {/* Previous button */}
          {lightboxIndex > 0 && (
            <button
              onClick={(e) => { e.stopPropagation(); goPrev(); }}
              className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center hover:bg-white/20 transition-colors"
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
              </svg>
            </button>
          )}

          {/* Next button */}
          {lightboxIndex < urls.length - 1 && (
            <button
              onClick={(e) => { e.stopPropagation(); goNext(); }}
              className="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center hover:bg-white/20 transition-colors"
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
              </svg>
            </button>
          )}

          {/* Image */}
          <img
            src={urls[lightboxIndex]}
            alt={`${locale === "zh" ? "场景" : "Scene"} ${lightboxIndex + 1}`}
            className="max-w-full max-h-full object-contain rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}
