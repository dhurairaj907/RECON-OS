"use client";

import React, { useEffect, useState } from "react";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { useSceneVisibility } from "@/components/spatial/three/useSceneVisibility";

const SRC = "/media/command-center-ambient.mp4";
const POSTER = "/media/command-center-ambient-poster.jpg";

/** Same treatment for both the <video> and its poster <img> fallback, so the
 * two never visibly swap: heavy desaturation + a hue shift off the source
 * clip's teal toward the app's periwinkle accent, blurred and dimmed until
 * it reads as atmosphere/texture rather than literal footage. */
const TREATMENT: React.CSSProperties = {
  filter:
    "grayscale(0.6) saturate(1.3) hue-rotate(55deg) brightness(0.55) contrast(1.1) blur(6px)",
};

/**
 * Ambient background layer for the Command Center hero only. Desktop +
 * motion-allowed + on-screen ⇒ the treated video loop plays (muted, no
 * controls, `preload="none"` until visible so it never loads on routes/
 * viewports that won't show it). Everywhere else ⇒ a static treated poster
 * frame, never both, never neither. Purely decorative (`aria-hidden`),
 * mounted behind the WebGL spatial field and its scrim.
 */
export function AmbientVideo() {
  const reducedMotion = usePrefersReducedMotion();
  const { ref, active } = useSceneVisibility<HTMLDivElement>();
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setIsDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const wantsVideo = isDesktop && !reducedMotion && active;

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden opacity-20"
    >
      {wantsVideo ? (
        <video
          key="video"
          className="h-full w-full object-cover"
          style={TREATMENT}
          src={SRC}
          poster={POSTER}
          autoPlay
          loop
          muted
          playsInline
          preload="none"
        />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key="poster"
          className="h-full w-full object-cover"
          style={TREATMENT}
          src={POSTER}
          alt=""
        />
      )}
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(to right, rgb(var(--c-bg)) 0%, transparent 40%, rgb(var(--c-bg) / 0.5) 100%)",
          mixBlendMode: "multiply",
        }}
      />
    </div>
  );
}
