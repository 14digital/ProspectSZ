import "./globals.css";import {AppShell} from "@/components/AppShell";
export const metadata={title:"ProspectSZ · 14Digital",description:"Human-reviewed UK care sales outreach"};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body><AppShell>{children}</AppShell></body></html>}
