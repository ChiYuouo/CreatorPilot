import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { BarChart3, Bot, Clapperboard, FileVideo, LayoutDashboard, LogOut, Timer, UploadCloud, UsersRound } from "lucide-react";

import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import "@/styles/console.css";

const nav = [
  { label: "总览", path: "/", icon: LayoutDashboard },
  { label: "素材库", path: "/media", icon: FileVideo },
  { label: "发布", path: "/publishing", icon: UploadCloud },
  { label: "账号管理", path: "/accounts", icon: UsersRound },
  { label: "自动化", path: "/automation", icon: Timer },
  { label: "分析", path: "/analytics", icon: BarChart3 },
  { label: "Agent", path: "/agent", icon: Bot },
];

const preloadPage: Record<string, () => Promise<unknown>> = {
  "/": () => import("@/pages/Dashboard"),
  "/media": () => import("@/pages/MediaLibrary"),
  "/publishing": () => import("@/pages/Publishing"),
  "/accounts": () => import("@/pages/PlatformAccounts"),
  "/automation": () => import("@/pages/Automation"),
  "/analytics": () => import("@/pages/Analytics"),
  "/agent": () => import("@/pages/AgentChat"),
};
const prefetch = (path: string) => { void preloadPage[path]().catch(() => undefined); };

export function ConsoleBackdrop() {
  return <div className="cp-backdrop" aria-hidden="true" />;
}

export default function ConsoleLayout({ children, eyebrow, title, description, actions, className = "" }: {
  children: ReactNode;
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  className?: string;
}) {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const clear = useAuthStore((state) => state.clear);
  return <div className="cp-console cp-shell">
    <div className="cp-shell-content">
      <aside className="cp-nav-wrap">
        <div className="cp-pill-nav">
          <div className="cp-brand"><span className="cp-brand-mark"><Clapperboard size={18} /></span><strong>CreatorPilot</strong></div>
          <div className="cp-nav-label">工作区</div>
          <nav className="cp-nav-links" aria-label="主导航">{nav.map((item) => <NavLink key={item.path} to={item.path} end={item.path === "/"} viewTransition title={item.label} aria-label={item.label} onPointerEnter={() => prefetch(item.path)} onFocus={() => prefetch(item.path)} className={({ isActive }) => `cp-nav-item${isActive ? " active" : ""}`}><item.icon size={17} /><span>{item.label}</span></NavLink>)}</nav>
          <div className="cp-nav-account"><span className="cp-account-avatar" aria-hidden="true">{(user?.nickname || "创").slice(0, 1)}</span><span className="cp-account-name" title={user?.email}>{user?.nickname || "创作者"}<small>{user?.email || "当前账号"}</small></span><Button type="button" variant="ghost" size="icon" title="退出登录" aria-label="退出登录" onClick={() => { clear(); navigate("/login", { replace: true }); }}><LogOut size={16} /></Button></div>
        </div>
      </aside>
      <div className="cp-workspace">
        <header className="cp-topbar"><span>工作区 <span className="cp-topbar-separator">/</span> {title}</span><span>内容运营控制台</span></header>
        <main className={`cp-main ${className}`}>
          <div className="cp-page-header"><div><div className="cp-eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{actions && <div className="cp-header-actions">{actions}</div>}</div>
          {children}
        </main>
      </div>
    </div>
  </div>;
}
