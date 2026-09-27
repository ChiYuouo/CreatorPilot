import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Clapperboard } from "lucide-react";
import { ConsoleBackdrop } from "@/components/ConsoleLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

export default function Login() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("请输入邮箱和密码");
      return;
    }
    setLoading(true);
    try {
      const { data } = await authApi.login({ email, password });
      setAuth(data.access_token, data.refresh_token, data.user);
      navigate("/", { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.message ?? "登录失败，请稍后重试";
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="cp-shell cp-auth">
      <ConsoleBackdrop />
      <div className="cp-auth-panel">
        <div className="cp-auth-brand"><span className="cp-brand-mark"><Clapperboard size={17} /></span>CreatorPilot</div>
        <span className="cp-auth-eyebrow">CREATOR OPERATIONS</span>
        <h1>欢迎回来，继续<em>创作</em></h1>
        <p>登录你的内容运营工作台</p>
          <form onSubmit={onSubmit} className="cp-auth-form">
            <div>
              <label htmlFor="email">邮箱</label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>
            <div>
              <label htmlFor="password">密码</label>
              <Input
                id="password"
                type="password"
                placeholder="密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            <Button type="submit" disabled={loading} aria-busy={loading}>
              {loading ? "登录中…" : "登录"}
            </Button>
            <div className="cp-auth-switch">还没有账号？ <Link to="/register">注册账号</Link></div>
          </form>
      </div>
    </div>
  );
}
