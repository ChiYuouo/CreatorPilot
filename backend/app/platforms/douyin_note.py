"""抖音图文表单兼容层；不修改 vendored 上传器，也不接管提交步骤。"""
from typing import Any


class DouyinNoteFormError(RuntimeError):
    """图文填写阶段失败，尚未调用发布按钮。"""


def note_uploader_class(vendor_class: type) -> type:
    """只覆盖图文的字段定位，视频继续沿用上游实现。"""
    class CompatibleDouyinNote(vendor_class):
        async def fill_title_and_description(
            self, page: Any, title: str, description: str, tags: list[str] | None = None,
        ) -> None:
            try:
                # 实测图文页是“添加作品标题”，视频页仍为“填写作品标题”。
                title_input = page.locator(
                    'input[placeholder="添加作品标题"], input[placeholder*="填写作品标题"]'
                ).first
                await title_input.wait_for(state="visible", timeout=30000)
                await title_input.fill(title)
                editor = page.locator('div.zone-container[contenteditable="true"]').first
                await editor.wait_for(state="visible", timeout=30000)
                await editor.fill(description.strip())
                await editor.click()
                await page.keyboard.press("Control+End")
                for tag in tags or []:
                    await page.keyboard.type(" #" + tag)
                    await page.keyboard.press("Space")
                await page.keyboard.press("Escape")
            except Exception as exc:
                raise DouyinNoteFormError("抖音图文标题或正文填写失败，未点击发布按钮；请检查平台页面后重新提交") from exc
    return CompatibleDouyinNote
