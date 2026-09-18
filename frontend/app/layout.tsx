import type { Metadata } from "next";
import "@fontsource-variable/manrope";
import "./globals.css";
export const metadata: Metadata = { title: "DoorLens — recorded door analysis", description: "Classify recorded door movements and explore explicit recording assumptions. Local, reproducible door telemetry analysis." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
