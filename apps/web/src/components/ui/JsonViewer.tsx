"use client";

import React, { useState } from "react";
import { Check, Copy } from "lucide-react";

interface JsonViewerProps {
  data: any;
  title?: string;
  maxHeight?: string;
}

export function JsonViewer({ data, title, maxHeight = "400px" }: JsonViewerProps) {
  const [copied, setCopied] = useState(false);
  const jsonString = JSON.stringify(data, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-lg border border-border bg-surface-subtle overflow-hidden">
      <div className="flex items-center justify-between px-3.5 py-2 bg-surface border-b border-border text-xs text-fg-muted font-mono">
        <span>{title || "PAYLOAD (JSON)"}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-fg transition-colors text-fg-muted"
          title="Copy JSON"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-status-success" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre
        style={{ maxHeight }}
        className="p-4 text-xs font-mono text-fg-secondary overflow-auto whitespace-pre leading-relaxed select-text"
      >
        {jsonString}
      </pre>
    </div>
  );
}
