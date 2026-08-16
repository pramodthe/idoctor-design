import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "iDoctor Design — KRAS G12C binder loop",
  description:
    "Reads how sotorasib fails, designs binders under those constraints, and only keeps designs it cannot disprove.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
    >
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
