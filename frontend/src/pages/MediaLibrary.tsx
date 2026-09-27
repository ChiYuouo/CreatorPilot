import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { FileVideo, Image as ImageIcon, UploadCloud } from "lucide-react";
import { toast } from "sonner";

import { publishingApi, type MediaAsset } from "@/api/publishing";
import ConsoleLayout from "@/components/ConsoleLayout";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function message(error: unknown, fallback: string) {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { message?: string } } }).response;
    if (response?.data?.message) return response.data.message;
  }
  return fallback;
}

export default function MediaLibrary() {
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [filter, setFilter] = useState<"all" | "image" | "video">("all");
  const [search, setSearch] = useState("");
  const [preview, setPreview] = useState<MediaAsset | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewRetry, setPreviewRetry] = useState(0);

  useEffect(() => {
    setPreviewUrl(""); setPreviewError("");
    if (!preview) return;
    const controller = new AbortController();
    if (preview.media_type === "video") {
      publishingApi.videoPreview(preview.id, controller.signal).then((data) => {
        if (!controller.signal.aborted) setPreviewUrl(data.url);
      }).catch(() => { if (!controller.signal.aborted) setPreviewError("视频预览加载失败，请重试"); });
      return () => controller.abort();
    }
    let objectUrl = "";
    publishingApi.imgPreview(preview.id, controller.signal).then((blob) => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setPreviewUrl(objectUrl);
    }).catch(() => { if (!controller.signal.aborted) setPreviewError("图片预览失败，请重试"); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [preview, previewRetry]);

  useEffect(() => {
    let active = true;
    publishingApi.assets()
      .then((items) => { if (active) { setAssets(items); setError(""); } })
      .catch((cause) => { if (active) setError(message(cause, "素材加载失败")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    const image = /\.(jpe?g|png|webp)$/i.test(file.name);
    if (file.size > (image ? 20 : 512) * 1024 * 1024) {
      toast.error(image ? "图片不能超过 20 MB" : "视频不能超过 512 MB"); return;
    }
    setUploading(true);
    try {
      const asset = await publishingApi.upload(file);
      setAssets((items) => [asset, ...items]);
      setFile(null);
      setUploadOpen(false);
      toast.success(`${asset.media_type === "image" ? "图片" : "视频"}已加入素材库`);
    } catch (cause) { toast.error(message(cause, "素材上传失败")); }
    finally { setUploading(false); }
  };

  const visible = assets.filter((asset) => (filter === "all" || asset.media_type === filter) && asset.filename.toLowerCase().includes(search.toLowerCase()));
  const hints = "视频支持 MP4、MOV、M4V、WebM（最大 512 MB）；图片支持 JPG、PNG、WebP（最大 20 MB，4000 万像素）。";

  return <ConsoleLayout eyebrow="CONTENT / MEDIA" title="素材库" description="集中管理图片与视频素材" actions={<Button onClick={() => { setFile(null); setUploadOpen(true); }}><UploadCloud size={15} />上传素材</Button>}>
    {error && <div className="cp-error">{error}</div>}
    <section className="cp-panel">
      <div className="cp-panel-head"><div><h2>全部素材</h2><p>图片和视频均可预览，并可在发布中心选择使用</p></div><span className="cp-muted">{assets.length} 个素材</span></div>
      <div className="mb-4 flex flex-wrap items-center gap-2">{(["all", "video", "image"] as const).map((type) => <Button key={type} size="sm" variant={filter === type ? "default" : "outline"} onClick={() => setFilter(type)}>{type === "all" ? "全部" : type === "video" ? "视频" : "图片"}</Button>)}<Input className="max-w-xs" placeholder="搜索素材名称" aria-label="搜索素材" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
      {loading && <p className="cp-muted">加载中…</p>}
      {!loading && (visible.length === 0
        ? <div className="cp-empty"><ImageIcon size={28} />{assets.length ? "没有匹配的素材" : "暂无素材，点击“上传素材”添加图片或视频"}</div>
        : <div className="cp-media-grid">{visible.map((asset) => <div key={asset.id} className="cp-media-card">
          <div className="cp-media-icon">{asset.media_type === "image" ? <ImageIcon size={22} /> : <FileVideo size={22} />}</div>
          <div className="min-w-0 flex-1"><div className="truncate text-sm font-medium" title={asset.filename}>{asset.filename}</div><div className="mt-1 text-xs text-muted-foreground">{asset.media_type === "image" ? "图片" : "视频"} · {(asset.size_bytes / 1024 / 1024).toFixed(1)} MB · {new Date(asset.created_at).toLocaleString("zh-CN")}</div></div>
          <Button size="sm" variant="ghost" onClick={() => setPreview(asset)} aria-label={`预览 ${asset.filename}`}>预览</Button>
        </div>)}</div>)}
    </section>
    <div className="cp-hint">{hints} 视频可前往 <Link to="/publishing" className="cp-panel-link">发布中心</Link> 提交；图文可在发布中心选择多张图片，提交至抖音、小红书或快手。</div>
    <Dialog open={uploadOpen} onOpenChange={(open) => { if (!uploading) setUploadOpen(open); }} title="上传素材" description={hints} className="max-w-lg">
      <form onSubmit={upload} className="space-y-5"><div><Label htmlFor="media-file">选择图片或视频</Label><Input id="media-file" type="file" accept=".mp4,.mov,.m4v,.webm,.jpg,.jpeg,.png,.webp" disabled={uploading} onChange={(event) => setFile(event.target.files?.[0] ?? null)} required /></div><div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={uploading} onClick={() => setUploadOpen(false)}>取消</Button><Button type="submit" disabled={!file || uploading} aria-busy={uploading}>{uploading ? "上传中…" : "上传到素材库"}</Button></div></form>
    </Dialog>
    <Dialog open={preview !== null} onOpenChange={(open) => { if (!open) setPreview(null); }} title={preview?.media_type === "video" ? "视频预览" : "图片预览"} description={preview?.filename}>
      {previewError ? <div className="space-y-3"><p className="text-sm text-destructive">{previewError}</p><Button variant="outline" onClick={() => setPreviewRetry((value) => value + 1)}>重新加载预览</Button></div> : previewUrl ? preview?.media_type === "video" ? <video key={previewUrl} src={previewUrl} controls preload="metadata" className="mx-auto max-h-[65vh] w-full" onError={() => setPreviewError("视频无法播放，可能是浏览器不支持该编码或预览凭证已过期。可重新加载；仍失败时建议使用 H.264 编码的 MP4。")} /> : <img src={previewUrl} alt={preview?.filename ?? "图片素材"} className="mx-auto max-h-[65vh] max-w-full object-contain" /> : <p className="text-sm text-muted-foreground">加载中…</p>}
    </Dialog>
  </ConsoleLayout>;
}
