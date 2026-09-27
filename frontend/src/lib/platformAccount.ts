const platformNames: Record<string, string> = {
  douyin: "抖音",
  kuaishou: "快手",
  xiaohongshu: "小红书",
  tencent: "视频号",
  bilibili: "B 站",
};

export const creatorUploadUrls: Record<string, string> = {
  douyin: "https://creator.douyin.com/creator-micro/content/upload",
  kuaishou: "https://cp.kuaishou.com/article/publish/video",
  xiaohongshu: "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video",
  tencent: "https://channels.weixin.qq.com/platform/post/create",
  bilibili: "https://member.bilibili.com/platform/upload/video/frame",
};

export function platformName(platform: string) {
  return platformNames[platform] ?? platform;
}

export function accountLabel(account: { id: number; platform: string; remark: string | null }) {
  return account.remark || `${platformName(account.platform)} #${account.id}`;
}
