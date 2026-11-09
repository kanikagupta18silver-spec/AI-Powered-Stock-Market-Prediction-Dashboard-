import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MarketLens | Stock intelligence",
  description:
    "Research public market history and compare transparent stock forecasts.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
