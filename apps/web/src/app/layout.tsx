import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "RECON OS — Revenue Recovery Command Center",
  description: "Autonomous AI Revenue Recovery and Optimization Operating System for the Razorpay Ecosystem",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
