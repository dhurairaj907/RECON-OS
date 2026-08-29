"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Tracks whether an element is on screen. The 3D <Canvas> uses this to switch
 * its render loop between "always" and "never" so an off-screen scene costs
 * nothing. Also reports document visibility (tab hidden ⇒ paused).
 */
export function useSceneVisibility<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let onScreen = false;
    const recompute = () => setActive(onScreen && !document.hidden);

    const io = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        recompute();
      },
      { threshold: 0.12 }
    );
    io.observe(el);
    document.addEventListener("visibilitychange", recompute);

    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", recompute);
    };
  }, []);

  return { ref, active };
}
