import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, QrCode, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { publishingApi, type LoginSession, type PlatformAccount, type PublishingPlatform } from "@/api/publishing";
import ConsoleLayout from "@/components/ConsoleLayout";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { SelectField } from "@/components/ui/select";
import { accountLabel, creatorUploadUrls, platformName } from "@/lib/platformAccount";

const statusText: Record<PlatformAccount["status"], string> = {
  valid: "已连接", expired: "已失效", unchecked: "待检查",
};

function message(error: unknown, fallback: string) {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { message?: string } } }).response;
    if (response?.data?.message) return response.data.message;
  }
  return fallback;
}

export default function PlatformAccounts() {
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [platforms, setPlatforms] = useState<PublishingPlatform[]>([]);
  const [loginPlatform, setLoginPlatform] = useState("douyin");
  const [accountRemark, setAccountRemark] = useState("");
  const [editingAccount, setEditingAccount] = useState<PlatformAccount | null>(null);
  const [editedRemark, setEditedRemark] = useState("");
  const [reloginAccount, setReloginAccount] = useState<PlatformAccount | null>(null);
  const [loginSession, setLoginSession] = useState<LoginSession | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const loginAttempt = useRef(0);
  const accountRemarkRef = useRef("");
  const sessionRef = useRef<LoginSession | null>(null);

  useEffect(() => { sessionRef.current = loginSession; }, [loginSession]);
  useEffect(() => () => {
    loginAttempt.current += 1;
    const session = sessionRef.current;
    if (session && !["success", "failed", "cancelled"].includes(session.status)) {
      void publishingApi.cancelLogin(session.id).catch(() => undefined);
    }
  }, []);

  const refresh = async () => {
    try {
      const [nextAccounts, nextPlatforms] = await Promise.all([publishingApi.accounts(), publishingApi.platforms()]);
      setAccounts(nextAccounts);
      setPlatforms(nextPlatforms);
      setError("");
    } catch (cause) {
      setError(message(cause, "账号列表加载失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(); }, []);

  useEffect(() => {
    if (!accountOpen || !loginSession?.id || ["success", "failed", "cancelled"].includes(loginSession.status)) return;
    let stopped = false;
    let polling = false;
    const pollStatus = async () => {
      if (polling) return;
      polling = true;
      try {
        const next = await publishingApi.loginSession(loginSession.id, reloginAccount ? undefined : accountRemarkRef.current);
        if (stopped) return;
        setLoginSession(next);
        if (next.status === "success") {
          setAccountOpen(false);
          setReloginAccount(null);
          setLoginSession(null);
          await refresh();
          toast.success("扫码登录成功，账号已绑定");
        }
      } catch (cause) {
        if (!stopped) toast.error(message(cause, "获取扫码状态失败"));
      } finally { polling = false; }
    };
    void pollStatus();
    const timer = window.setInterval(() => void pollStatus(), 1500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [accountOpen, loginSession?.id, loginSession?.status]);

  const closeAccountDialog = () => {
    loginAttempt.current += 1;
    setBusy("");
    if (loginSession && !["success", "failed", "cancelled"].includes(loginSession.status)) {
      void publishingApi.cancelLogin(loginSession.id).catch(() => undefined);
    }
    setAccountOpen(false);
    setLoginSession(null);
    setReloginAccount(null);
  };

  const beginLogin = async () => {
    const attempt = ++loginAttempt.current;
    const previous = loginSession;
    setLoginSession(null);
    setBusy("login");
    try {
      if (previous && !["success", "failed", "cancelled"].includes(previous.status)) {
        await publishingApi.cancelLogin(previous.id);
      }
      const session = reloginAccount
        ? await publishingApi.restartLogin(reloginAccount.id)
        : await publishingApi.startLogin(loginPlatform, accountRemark);
      if (attempt !== loginAttempt.current) {
        void publishingApi.cancelLogin(session.id).catch(() => undefined);
        return;
      }
      setLoginSession(session);
    } catch (cause) {
      if (attempt === loginAttempt.current) toast.error(message(cause, "扫码登录启动失败"));
    } finally {
      if (attempt === loginAttempt.current) setBusy("");
    }
  };

  const checkAllAccounts = async () => {
    const startedAt = performance.now();
    setBusy("check-all");
    try {
      const result = await publishingApi.checkAllAccounts();
      await refresh();
      toast.success(`已检测 ${result.accounts.length} 个账号${result.failed_ids.length ? `，${result.failed_ids.length} 个检测未完成` : ""}`);
    } catch (cause) { toast.error(message(cause, "批量检查失败")); }
    finally {
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(0, 650 - (performance.now() - startedAt))));
      setBusy("");
    }
  };

  const clearExpiredAccounts = async () => {
    setBusy("clear-expired");
    try {
      const result = await publishingApi.clearExpiredAccounts();
      await refresh();
      toast.success(`已清理 ${result.deleted_count} 个失效账号`);
    } catch (cause) { toast.error(message(cause, "清理失效账号失败")); }
    finally { setBusy(""); }
  };

  const deleteAccount = async (id: number) => {
    setBusy(`delete-${id}`);
    try {
      await publishingApi.deleteAccount(id);
      await refresh();
      toast.success("账号已从列表移除，历史发布任务已保留");
    } catch (cause) { toast.error(message(cause, "删除账号失败")); }
    finally { setBusy(""); }
  };

  const checkAccount = async (id: number) => {
    const startedAt = performance.now();
    setBusy(`check-${id}`);
    try {
      const account = await publishingApi.checkAccount(id);
      setAccounts((items) => items.map((item) => item.id === id ? account : item));
      toast[account.status === "valid" ? "success" : "error"](account.status === "valid" ? "登录态有效" : "登录态已失效，请在本机重新扫码");
    } catch (cause) { toast.error(message(cause, "登录态检查失败")); }
    finally {
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(0, 650 - (performance.now() - startedAt))));
      setBusy("");
    }
  };

  const saveRemark = async () => {
    if (!editingAccount) return;
    setBusy("remark");
    try {
      const updated = await publishingApi.updateAccountRemark(editingAccount.id, editedRemark);
      setAccounts((items) => items.map((item) => item.id === updated.id ? updated : item));
      setEditingAccount(null);
      toast.success("账号备注已更新");
    } catch (cause) { toast.error(message(cause, "修改备注失败")); }
    finally { setBusy(""); }
  };

  return <ConsoleLayout eyebrow="PUBLISHING / ACCOUNTS" title="账号管理" description="绑定和维护用于发布的创作者平台账号" actions={<Button onClick={() => {
    setReloginAccount(null); setLoginSession(null); setLoginPlatform("douyin");
    setAccountRemark(""); accountRemarkRef.current = ""; setAccountOpen(true);
  }}><QrCode size={15} />绑定账号</Button>}>
    {error && <div className="cp-error">{error}</div>}
    <section className="cp-panel">
      <div className="cp-panel-head">
        <div><h2>已绑定账号</h2><p>定期检查登录状态；失效后可在本机重新扫码</p></div>
        <span className="cp-muted">{accounts.length} 个账号</span>
      </div>
      <div className="cp-row mb-4">
        <Button variant="outline" size="sm" disabled={busy !== "" || accounts.length === 0} aria-busy={busy === "check-all"} onClick={() => void checkAllAccounts()}><RefreshCw size={14} className={busy === "check-all" ? "cp-spinning" : ""} />{busy === "check-all" ? "检测中…" : "检测所有账号"}</Button>
        <Button variant="outline" size="sm" disabled={busy !== "" || !accounts.some((account) => account.status === "expired")} aria-busy={busy === "clear-expired"} onClick={() => void clearExpiredAccounts()}>{busy === "clear-expired" ? "清理中…" : "清理失效账号"}</Button>
      </div>
      {loading && <p className="cp-muted">加载中…</p>}
      {!loading && (accounts.length ? accounts.map((account) => {
        const name = platformName(account.platform);
        const label = accountLabel(account);
        return <div className="cp-account-line" key={account.id}>
        <div><strong>{creatorUploadUrls[account.platform]
          ? <a href={creatorUploadUrls[account.platform]} target="_blank" rel="noopener noreferrer" className="cp-panel-link" title={`打开${name}创作者后台`}>{label}</a>
          : label}</strong><small>{name} · {account.remark ? `编号 #${account.id} · ` : ""}{account.checked_at ? `上次检查 ${new Date(account.checked_at).toLocaleString("zh-CN")}` : "尚未检查"}</small></div>
        <div className="cp-row">
          <span className={`cp-badge ${account.status}`}>{statusText[account.status]}</span>
          <Button variant="outline" size="sm" disabled={busy !== ""} aria-busy={busy === `check-${account.id}`} onClick={() => void checkAccount(account.id)}><RefreshCw size={14} className={busy === `check-${account.id}` ? "cp-spinning" : ""} />{busy === `check-${account.id}` ? "检查中…" : "检查"}</Button>
          <Button variant="outline" size="sm" disabled={busy !== ""} onClick={() => { setEditingAccount(account); setEditedRemark(account.remark ?? ""); }}><Pencil size={14} />备注</Button>
          <Button variant="outline" size="sm" disabled={busy !== ""} onClick={() => {
            setReloginAccount(account); setLoginPlatform(account.platform);
            setAccountRemark(account.remark ?? ""); accountRemarkRef.current = account.remark ?? "";
            setLoginSession(null); setAccountOpen(true);
          }}>重新登录</Button>
          <Button variant="outline" size="sm" disabled={busy !== ""} aria-label={`删除账号 ${label}`} onClick={() => void deleteAccount(account.id)}><Trash2 size={14} /></Button>
        </div>
      </div>}) : <div className="cp-empty"><ShieldCheck size={26} />暂无账号，点击“绑定账号”开始扫码登录</div>)}
    </section>
    <div className="cp-hint">点击账号名称会在新标签页打开平台创作者后台，浏览器可能需要另行登录。账号有排队、上传中或待核实的预约任务时无法删除。发布任务请在 <Link to="/publishing" className="cp-panel-link">发布中心</Link> 查看。</div>
    <Dialog open={editingAccount !== null} onOpenChange={(open) => { if (!open && busy !== "remark") setEditingAccount(null); }} title="修改账号备注" description="备注仅用于在 CreatorPilot 中识别账号；清空后显示平台名称和账号编号。" className="max-w-md">
      <form onSubmit={(event) => { event.preventDefault(); void saveRemark(); }} className="space-y-4">
        <div className="cp-field"><label htmlFor="cp-edit-account-remark">账号备注</label><Input id="cp-edit-account-remark" maxLength={100} value={editedRemark} onChange={(event) => setEditedRemark(event.target.value)} placeholder="例如：品牌主号" /></div>
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={busy === "remark"} onClick={() => setEditingAccount(null)}>取消</Button><Button type="submit" disabled={busy === "remark"}>{busy === "remark" ? "保存中…" : "保存"}</Button></div>
      </form>
    </Dialog>
    <Dialog open={accountOpen} onOpenChange={(open) => { if (!open) closeAccountDialog(); else setAccountOpen(true); }} title={reloginAccount ? "重新登录账号" : "绑定平台账号"} description="确认平台和备注后点击登录，浏览器会弹出窗口供扫码。" className="max-w-lg">
      <div className="space-y-4">
        <div className="cp-field"><label htmlFor="cp-login-platform">平台</label><SelectField id="cp-login-platform" value={loginPlatform} onValueChange={setLoginPlatform} options={platforms.map((item) => ({ value: item.key, label: item.name }))} disabled={!!reloginAccount || !!loginSession} /><small>当前开放平台由服务端注册表提供。</small></div>
        {!reloginAccount && <div className="cp-field"><label htmlFor="cp-account-remark">账号备注（可选）</label><Input id="cp-account-remark" placeholder="例如：品牌主号" maxLength={100} value={accountRemark} onChange={(event) => { setAccountRemark(event.target.value); accountRemarkRef.current = event.target.value; }} /></div>}
        {busy === "login" && <div className="cp-hint">正在启动浏览器，请稍候…</div>}
        {!loginSession && busy !== "login" && <div className="cp-hint">{loginPlatform === "bilibili" ? "点击「登录账号」后会弹出 B 站扫码终端，请在窗口里完成扫码。" : "点击「登录账号」后会弹出浏览器窗口，请在弹出的窗口里扫码。"}</div>}
        {loginSession && loginSession.status !== "failed" && <div className="cp-hint">{loginPlatform === "bilibili" ? "请在弹出的 B 站扫码终端完成登录；成功后终端会关闭。" : `已打开浏览器窗口，请在窗口里用${platforms.find((item) => item.key === loginPlatform)?.name ?? loginPlatform} App 扫码；扫码后在手机上点确认，成功后窗口会自动关闭。`}</div>}
        {loginSession?.status === "failed" && <div className="cp-error">{loginSession.message || "登录失败，请重试"}</div>}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={closeAccountDialog}>取消</Button><Button type="button" disabled={busy !== ""} aria-busy={busy === "login"} onClick={() => void beginLogin()}><QrCode size={15} />{busy === "login" ? "启动中…" : "登录账号"}</Button></div>
      </div>
    </Dialog>
  </ConsoleLayout>;
}
