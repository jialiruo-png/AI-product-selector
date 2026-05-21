#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from tkinter import ttk


ROOT = Path(__file__).resolve().parents[2]
COLLECT_ANY = ROOT / "采集工作台" / "scripts" / "collect_any.py"
DEFAULT_CANDIDATE_LIMIT = "10"
DEFAULT_DOWNLOAD_LIMIT = "3"

PLATFORMS = {
    "公众号": "weixin",
    "小红书": "xiaohongshu",
    "知乎": "zhihu",
    "GitHub": "github",
}


def clean_number(value: str, default: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    return digits or default


def open_finder(path: str) -> None:
    if path:
        subprocess.run(["open", path], check=False)


class MaterialCollectorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI 素材采集")
        self.geometry("760x680")
        self.minsize(680, 600)

        self.platform_var = tk.StringVar(value="小红书")
        self.candidate_var = tk.StringVar(value=DEFAULT_CANDIDATE_LIMIT)
        self.download_var = tk.StringVar(value=DEFAULT_DOWNLOAD_LIMIT)
        self.status_var = tk.StringVar(value="准备就绪")
        self.output_dir = ""
        self.running = False

        self._build_ui()
        self.after(100, self._bring_to_front)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(root, text="AI 素材采集控制台", font=("PingFang SC", 20, "bold"))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(root, text="输入链接或关键词，选择平台和数量，点击开始后自动筛选并保存 Markdown。")
        subtitle.pack(anchor=tk.W, pady=(4, 16))

        form = ttk.Frame(root)
        form.pack(fill=tk.BOTH, expand=False)
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="链接").grid(row=0, column=0, sticky=tk.W)
        self.links_text = tk.Text(form, height=7, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.links_text.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(6, 14))
        self.links_text.insert("1.0", "")

        ttk.Label(form, text="关键词").grid(row=2, column=0, sticky=tk.W)
        self.keyword_entry = ttk.Entry(form)
        self.keyword_entry.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(6, 14))

        ttk.Label(form, text="平台").grid(row=4, column=0, sticky=tk.W)
        platform_frame = ttk.Frame(form)
        platform_frame.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(6, 14))
        for label in PLATFORMS:
            ttk.Radiobutton(platform_frame, text=label, value=label, variable=self.platform_var).pack(side=tk.LEFT, padx=(0, 18))

        number_frame = ttk.Frame(form)
        number_frame.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(0, 14))
        number_frame.columnconfigure(0, weight=1)
        number_frame.columnconfigure(1, weight=1)

        ttk.Label(number_frame, text="筛选数量").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(number_frame, text="下载数量").grid(row=0, column=1, sticky=tk.W, padx=(16, 0))

        self.candidate_entry = ttk.Entry(number_frame, textvariable=self.candidate_var)
        self.candidate_entry.grid(row=1, column=0, sticky=tk.EW, pady=(6, 0))
        self.download_entry = ttk.Entry(number_frame, textvariable=self.download_var)
        self.download_entry.grid(row=1, column=1, sticky=tk.EW, padx=(16, 0), pady=(6, 0))

        hint = ttk.Label(
            form,
            text="规则：填了链接就按链接采集；没填链接就按关键词搜索。关键词模式会先看筛选数量，再下载数据更好的内容。",
            foreground="#555555",
            wraplength=700,
        )
        hint.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(0, 16))

        action_frame = ttk.Frame(root)
        action_frame.pack(fill=tk.X, pady=(8, 12))
        self.start_button = ttk.Button(action_frame, text="开始采集", command=self.start_collect)
        self.start_button.pack(side=tk.LEFT)
        self.open_button = ttk.Button(action_frame, text="打开输出目录", command=lambda: open_finder(self.output_dir), state=tk.DISABLED)
        self.open_button.pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(root, textvariable=self.status_var).pack(anchor=tk.W)

        ttk.Label(root, text="结果").pack(anchor=tk.W, pady=(14, 6))
        self.result_text = tk.Text(root, height=12, wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.result_text.pack(fill=tk.BOTH, expand=True)

    def _bring_to_front(self) -> None:
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(700, lambda: self.attributes("-topmost", False))
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to set frontmost of first process whose unix id is {os.getpid()} to true',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass

    def set_result(self, text: str) -> None:
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", text)

    def start_collect(self) -> None:
        if self.running:
            return

        links = self.links_text.get("1.0", tk.END).strip()
        keyword = self.keyword_entry.get().strip()
        input_text = links or keyword
        if not input_text:
            messagebox.showwarning("缺少输入", "请填写链接或关键词。")
            return

        platform = PLATFORMS[self.platform_var.get()]
        candidate_limit = clean_number(self.candidate_var.get(), DEFAULT_CANDIDATE_LIMIT)
        download_limit = clean_number(self.download_var.get(), DEFAULT_DOWNLOAD_LIMIT)

        self.running = True
        self.output_dir = ""
        self.open_button.configure(state=tk.DISABLED)
        self.start_button.configure(state=tk.DISABLED)
        self.status_var.set("正在采集，请稍等...")
        self.set_result("任务已开始。\n")

        thread = threading.Thread(
            target=self._run_collect,
            args=(platform, input_text, candidate_limit, download_limit),
            daemon=True,
        )
        thread.start()

    def _run_collect(self, platform: str, input_text: str, candidate_limit: str, download_limit: str) -> None:
        env = os.environ.copy()
        env["PATH"] = "/Users/ganhualiang/.local/bin:/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
        cmd = [
            str(COLLECT_ANY),
            "--platform",
            platform,
            "--input",
            input_text,
            "--candidate-limit",
            candidate_limit,
            "--limit",
            download_limit,
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
            output = proc.stdout.strip()
            self.after(0, self._finish_collect, proc.returncode, output)
        except Exception as exc:
            self.after(0, self._finish_collect, 1, f"运行失败：{exc}")

    def _finish_collect(self, status: int, output: str) -> None:
        self.running = False
        self.start_button.configure(state=tk.NORMAL)
        self.set_result(output or "没有输出。")

        success = self._extract_int(output, "成功文件")
        output_dir = self._extract_after_colon(output, "输出目录")
        self.output_dir = output_dir

        if status == 0 and success > 0:
            self.status_var.set(f"采集成功：{success} 个 Markdown 文件")
            if output_dir:
                self.open_button.configure(state=tk.NORMAL)
        else:
            reason = self._extract_after_colon(output, "失败原因") or "请查看结果区域。"
            self.status_var.set(f"采集失败：{reason}")

    @staticmethod
    def _extract_int(text: str, label: str) -> int:
        match = re.search(rf"{re.escape(label)}[：:]\s*(\d+)", text)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _extract_after_colon(text: str, label: str) -> str:
        for line in text.splitlines():
            if line.startswith(label):
                return re.split(r"[：:]", line, maxsplit=1)[-1].strip()
        return ""


def main() -> None:
    app = MaterialCollectorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
