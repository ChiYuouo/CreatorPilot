import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Clapperboard } from "lucide-react";
import { ConsoleBackdrop } from "@/components/ConsoleLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi } from "@/api/auth";

export default function Register() {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!nickname || !email || !password) {
      toast.error("请填写完整信息");
      return;
    }
    if (password.length < 8) {
      toast.error("密码至少 8 位");
      return;
    }
    setLoading(true);
    try {
      await authApi.register({ nickname, email, password });
      toast.success("注册成功，请登录");
      navigate("/login", { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.message ?? "注册失败，请稍后重试";
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
        <h1>开始你的<em>创作</em>工作流</h1>
        <p>创建账号，管理内容、发布与分析</p>
          <form onSubmit={onSubmit} className="cp-auth-form">
            <div>
              <label htmlFor="nickname">昵称</label>
              <Input
                id="nickname"
                placeholder="昵称"
                maxLength={64}
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                autoComplete="nickname" required
              />
            </div>
            <div>
              <label htmlFor="email">邮箱</label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email" required
              />
            </div>
            <div>
              <label htmlFor="password">密码</label>
              <Input
                id="password"
                type="password"
                placeholder="至少 8 位"
                maxLength={72}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password" required minLength={8}
              />
            </div>
            <Button type="submit" disabled={loading} aria-busy={loading}>
              {loading ? "注册中…" : "注册"}
            </Button>
            <div className="cp-auth-switch">已有账号？ <Link to="/login">登录</Link></div>
          </form>
      </div>
    </div>
  );
}
