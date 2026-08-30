"use client";

import React, { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

interface RevealProps extends React.HTMLAttributes<HTMLElement> {
  children: React.ReactNode;
  className?: string;
  /** ms delay before the transition starts (used for light stagger). */
  delay?: number;
  as?: keyof JSX.IntrinsicElements;
}

/**
 * Fast, operational entrance: opacity + 8px rise, ~220ms.
 * Instant (no transition) when reduced-motion is set — content always renders.
 * Uses one IntersectionObserver per instance; disconnects after first reveal.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
  ...rest
}: RevealProps) {
  const Tag = as as any;
  const ref = useRef<HTMLElement | null>(null);
  const [shown, setShown] = useState(false);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (reduced) {
      setShown(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { threshold: 0.08, rootMargin: "0px 0px -5% 0px" }
    );
    io.observe(el);
    // Failsafe: never leave content hidden if the observer never fires.
    const t = window.setTimeout(() => setShown(true), 400);
    return () => {
      io.disconnect();
      window.clearTimeout(t);
    };
  }, [reduced]);

  return (
    <Tag
      ref={ref as any}
      style={reduced ? undefined : { transitionDelay: `${delay}ms` }}
      className={cn(
        reduced
          ? ""
          : cn(
              "transition-[opacity,transform] duration-200 ease-spatial will-change-[opacity,transform]",
              shown ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
            ),
        className
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/**
 * Wraps a set of children and applies an incremental delay to each,
 * for a controlled cascade on grids / lists.
 */
export function RevealGroup({
  children,
  className,
  step = 40,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  step?: number;
  as?: keyof JSX.IntrinsicElements;
}) {
  const items = React.Children.toArray(children);
  const Tag = as as any;
  return (
    <Tag className={className}>
      {items.map((child, i) => (
        <Reveal key={i} delay={i * step}>
          {child}
        </Reveal>
      ))}
    </Tag>
  );
}
