import zipfile
import re
import json
import os
import time
import threading
import webbrowser
import concurrent.futures
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import requests

# 尝试导入拖拽支持库（可选）
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_DROP_AVAILABLE = True
except ImportError:
    DRAG_DROP_AVAILABLE = False

# ================== 全局配置 ==================
CONFIG = {
    'engine': 'mymemory',          # 默认引擎
    'target_lang': '简体中文',      # 默认目标语言
    'batch_size': 20,              # AI批量翻译每批条数（降低默认值以提高稳定性）
    'mymemory_api_key': '',
    'openai_api_key': '',
    'openai_model': 'gpt-4o-mini',
    'claude_api_key': '',
    'claude_model': 'claude-3-5-haiku-20241022',
    'gemini_api_key': '',
    'gemini_model': 'gemini-1.5-flash',
    'deepseek_api_key': '',
    'deepseek_model': 'deepseek-v4-flash',   # 已更新为有效模型名
    'local_api_url': 'http://localhost:11434/v1/chat/completions',
    'local_model': 'llama3',
    'local_api_key': '',
}
CONFIG_FILE = 'config.json'

# 语言选项：显示名称 -> {iso, mc, english}
LANGUAGES = {
    '简体中文':       {'iso': 'zh-CN', 'mc': 'zh_cn', 'english': 'Simplified Chinese'},
    '繁體中文':       {'iso': 'zh-TW', 'mc': 'zh_tw', 'english': 'Traditional Chinese'},
    '日文':           {'iso': 'ja',    'mc': 'ja_jp', 'english': 'Japanese'},
    '韩文':           {'iso': 'ko',    'mc': 'ko_kr', 'english': 'Korean'},
    '法文':           {'iso': 'fr',    'mc': 'fr_fr', 'english': 'French'},
    '德文':           {'iso': 'de',    'mc': 'de_de', 'english': 'German'},
    '西班牙文':       {'iso': 'es',    'mc': 'es_es', 'english': 'Spanish'},
    '俄文':           {'iso': 'ru',    'mc': 'ru_ru', 'english': 'Russian'},
    '葡萄牙文（巴西）': {'iso': 'pt-BR', 'mc': 'pt_br', 'english': 'Portuguese (Brazil)'},
}

# API 申请/文档网址
API_URLS = {
    'mymemory': 'https://mymemory.translated.net/doc/spec.php',
    'openai': 'https://platform.openai.com/api-keys',
    'claude': 'https://console.anthropic.com/settings/keys',
    'gemini': 'https://aistudio.google.com/app/apikey',
    'deepseek': 'https://platform.deepseek.com/api_keys',
    'local': 'https://ollama.com/',
}

# 引擎显示名称映射
ENGINE_DISPLAY = {
    'mymemory': 'MyMemory',
    'openai': 'OpenAI',
    'claude': 'Claude',
    'gemini': 'Gemini',
    'deepseek': 'DeepSeek',
    'local': '本地 AI',
}
ENGINE_DISPLAY_TO_ID = {v: k for k, v in ENGINE_DISPLAY.items()}

def log_message(msg, widget=None):
    if widget:
        widget.config(state='normal')
        widget.insert(tk.END, msg + "\n")
        widget.see(tk.END)
        widget.config(state='disabled')
    else:
        print(msg)

# ------------------ 单条翻译函数 ------------------
def translate_mymemory(text, target_lang, source='en'):
    api_key = CONFIG.get('mymemory_api_key', '')
    if not api_key:
        return text
    iso_code = LANGUAGES.get(target_lang, {}).get('iso', 'zh-CN')
    url = "https://api.mymemory.translated.net/get"
    params = {'q': text, 'langpair': f'{source}|{iso_code}', 'key': api_key}
    try:
        resp = requests.get(url, params=params, timeout=10)
        result = resp.json()
        if result.get('responseStatus') == 200:
            return result['responseData']['translatedText']
        else:
            return text
    except Exception as e:
        log_message(f"MyMemory 请求失败: {e}")
        return text

def translate_openai_single(text, target_lang, source='en'):
    api_key = CONFIG.get('openai_api_key', '')
    model = CONFIG.get('openai_model', 'gpt-4o-mini')
    if not api_key:
        return text
    target_name = LANGUAGES.get(target_lang, {}).get('english', 'Simplified Chinese')
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": f"Translate the following text from English to {target_name}. Only output the translation."},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        result = resp.json()
        if 'choices' in result and result['choices']:
            return result['choices'][0]['message']['content'].strip()
        else:
            return text
    except Exception as e:
        log_message(f"OpenAI 请求失败: {e}")
        return text

def translate_claude_single(text, target_lang, source='en'):
    api_key = CONFIG.get('claude_api_key', '')
    model = CONFIG.get('claude_model', 'claude-3-5-haiku-20241022')
    if not api_key:
        return text
    target_name = LANGUAGES.get(target_lang, {}).get('english', 'Simplified Chinese')
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    payload = {
        "model": model,
        "max_tokens": 1000,
        "system": f"Translate the following text from English to {target_name}. Only output the translation.",
        "messages": [{"role": "user", "content": text}]
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        result = resp.json()
        if 'content' in result and result['content']:
            return result['content'][0]['text'].strip()
        else:
            return text
    except Exception as e:
        log_message(f"Claude 请求失败: {e}")
        return text

def translate_gemini_single(text, target_lang, source='en'):
    api_key = CONFIG.get('gemini_api_key', '')
    model = CONFIG.get('gemini_model', 'gemini-1.5-flash')
    if not api_key:
        return text
    target_name = LANGUAGES.get(target_lang, {}).get('english', 'Simplified Chinese')
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": f"Translate the following text from English to {target_name}. Only output the translation.\n\n{text}"}]}]
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        result = resp.json()
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return text
    except Exception as e:
        log_message(f"Gemini 请求失败: {e}")
        return text

def translate_deepseek_single(text, target_lang, source='en'):
    api_key = CONFIG.get('deepseek_api_key', '')
    model = CONFIG.get('deepseek_model', 'deepseek-v4-flash')
    if not api_key:
        return text
    target_name = LANGUAGES.get(target_lang, {}).get('english', 'Simplified Chinese')
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": f"Translate the following text from English to {target_name}. Only output the translation."},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        result = resp.json()
        if 'choices' in result and result['choices']:
            return result['choices'][0]['message']['content'].strip()
        else:
            return text
    except Exception as e:
        log_message(f"DeepSeek 请求失败: {e}")
        return text

def translate_local_single(text, target_lang, source='en'):
    api_url = CONFIG.get('local_api_url', 'http://localhost:11434/v1/chat/completions')
    model = CONFIG.get('local_model', 'llama3')
    api_key = CONFIG.get('local_api_key', '')
    target_name = LANGUAGES.get(target_lang, {}).get('english', 'Simplified Chinese')
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": f"Translate the following text from English to {target_name}. Only output the translation."},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3
    }
    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=15)
        result = resp.json()
        if 'choices' in result and result['choices']:
            return result['choices'][0]['message']['content'].strip()
        else:
            return text
    except Exception as e:
        log_message(f"本地AI 请求失败: {e}")
        return text

def translate_text(text, target_lang, source='en'):
    engine = CONFIG.get('engine', 'mymemory')
    if engine == 'mymemory':
        return translate_mymemory(text, target_lang, source)
    elif engine == 'openai':
        return translate_openai_single(text, target_lang, source)
    elif engine == 'claude':
        return translate_claude_single(text, target_lang, source)
    elif engine == 'gemini':
        return translate_gemini_single(text, target_lang, source)
    elif engine == 'deepseek':
        return translate_deepseek_single(text, target_lang, source)
    elif engine == 'local':
        return translate_local_single(text, target_lang, source)
    else:
        return text

# ------------------ 占位符保护 ------------------
def protect_placeholders(text):
    placeholders = re.findall(r'%\d+\$[sd]|%[sd%]', text)
    for i, ph in enumerate(placeholders):
        text = text.replace(ph, f'<PH{i}>')
    return text, placeholders

def restore_placeholders(text, placeholders):
    for i, ph in enumerate(placeholders):
        text = text.replace(f'<PH{i}>', ph)
    return text

def translate_value(value, target_lang):
    protected, placeholders = protect_placeholders(value)
    translated = translate_text(protected, target_lang)
    return restore_placeholders(translated, placeholders)

# ------------------ AI 批量翻译函数 ------------------
def translate_batch_ai(translations_dict, target_lang, engine):
    if not translations_dict:
        return {}, []

    target_name = LANGUAGES.get(target_lang, {}).get('english', 'Simplified Chinese')
    json_input = json.dumps(translations_dict, ensure_ascii=False, indent=2)

    if engine == 'openai':
        api_key = CONFIG.get('openai_api_key', '')
        model = CONFIG.get('openai_model', 'gpt-4o-mini')
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        prompt = (
            f"Translate the values of the following JSON from English to {target_name}. "
            "Keep the keys unchanged and output only the JSON object, no extra text.\n\n"
            f"{json_input}"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a professional translator. Respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
    elif engine == 'claude':
        api_key = CONFIG.get('claude_api_key', '')
        model = CONFIG.get('claude_model', 'claude-3-5-haiku-20241022')
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        prompt = (
            f"Translate the values of the following JSON from English to {target_name}. "
            "Keep the keys unchanged and output only the JSON object, no extra text.\n\n"
            f"{json_input}"
        )
        payload = {
            "model": model,
            "max_tokens": 4000,
            "system": "You are a professional translator. Respond with valid JSON only.",
            "messages": [{"role": "user", "content": prompt}]
        }
    elif engine == 'gemini':
        api_key = CONFIG.get('gemini_api_key', '')
        model = CONFIG.get('gemini_model', 'gemini-1.5-flash')
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        prompt = (
            f"Translate the values of the following JSON from English to {target_name}. "
            "Keep the keys unchanged and output only the JSON object, no extra text.\n\n"
            f"{json_input}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
    elif engine == 'deepseek':
        api_key = CONFIG.get('deepseek_api_key', '')
        model = CONFIG.get('deepseek_model', 'deepseek-v4-flash')
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        prompt = (
            f"Translate the values of the following JSON from English to {target_name}. "
            "Keep the keys unchanged and output only the JSON object, no extra text.\n\n"
            f"{json_input}"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a professional translator. Respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
    elif engine == 'local':
        api_url = CONFIG.get('local_api_url', 'http://localhost:11434/v1/chat/completions')
        model = CONFIG.get('local_model', 'llama3')
        api_key = CONFIG.get('local_api_key', '')
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        prompt = (
            f"Translate the values of the following JSON from English to {target_name}. "
            "Keep the keys unchanged and output only the JSON object, no extra text.\n\n"
            f"{json_input}"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a professional translator. Respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
    else:
        return translations_dict, []

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        result = resp.json()

        if engine in ('openai', 'deepseek', 'local'):
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        elif engine == 'claude':
            content = result.get('content', [{}])[0].get('text', '')
        elif engine == 'gemini':
            content = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        else:
            content = ''

        # 去除可能的代码块围栏
        content = content.strip()
        if content.startswith('```'):
            first_newline = content.find('\n')
            if first_newline != -1:
                content = content[first_newline+1:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()

        start = content.find('{')
        end = content.rfind('}')
        if start == -1 or end == -1:
            raise ValueError("No JSON found in response")

        json_str = content[start:end+1]
        translated_dict = json.loads(json_str)

        failed_keys = []
        for key, original_value in translations_dict.items():
            if original_value.strip() and translated_dict.get(key) == original_value:
                failed_keys.append(key)

        return translated_dict, failed_keys

    except Exception as e:
        log_message(f"批量翻译失败，回退到逐条翻译。原因: {e}")
        return None, []

# ------------------ JAR 处理函数 ------------------
def find_lang_files(jar_path):
    lang_files = []
    with zipfile.ZipFile(jar_path, 'r') as jar:
        for file_info in jar.infolist():
            if '/lang/' in file_info.filename and file_info.filename.endswith(('en_us.lang', 'en_us.json')):
                lang_files.append(file_info.filename)
    return lang_files

def has_target_lang_file(jar_path, target_lang):
    mc_code = LANGUAGES.get(target_lang, {}).get('mc', 'zh_cn')
    target_suffixes = [f'{mc_code}.lang', f'{mc_code}.json']
    with zipfile.ZipFile(jar_path, 'r') as jar:
        for file_info in jar.infolist():
            if '/lang/' in file_info.filename:
                base = os.path.basename(file_info.filename)
                if base in target_suffixes:
                    return True
    return False

def parse_lang_content(content, is_json):
    translations = {}
    if is_json:
        data = json.loads(content.decode('utf-8'))
        translations.update(data)
    else:
        text = content.decode('utf-8', errors='replace')
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                translations[key.strip()] = value.strip()
    return translations

def generate_lang_file(translations, is_json):
    if is_json:
        return json.dumps(translations, ensure_ascii=False, indent=2).encode('utf-8')
    else:
        lines = []
        for key, value in translations.items():
            lines.append(f"{key}={value}")
        return '\n'.join(lines).encode('utf-8')

# ------------------ GUI 类 ------------------
class TranslatorApp:
    def __init__(self, root):
        self.root = root
        root.title("我的世界模组翻译工具 - 批量处理版")
        root.geometry("900x800")
        root.minsize(700, 600)
        root.resizable(True, True)

        # 使用 grid 布局，使界面自适应
        root.grid_rowconfigure(2, weight=1)   # 模组列表可扩展
        root.grid_rowconfigure(7, weight=1)   # 日志可扩展
        root.grid_columnconfigure(0, weight=1)

        # ---------- 第0行：添加文件、添加文件夹、清空列表 ----------
        file_btn_frame = tk.Frame(root)
        file_btn_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=(10,5))
        tk.Button(file_btn_frame, text="添加文件", command=self.add_files).pack(side=tk.LEFT, padx=5)
        tk.Button(file_btn_frame, text="添加文件夹", command=self.add_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(file_btn_frame, text="清空列表", command=self.clear_list).pack(side=tk.LEFT, padx=5)
        self.select_all_var = tk.BooleanVar(value=True)   # 默认全选                               

        # ---------- 第1行：折叠/展开模组列表按钮 ----------
        self.collapse_btn = tk.Button(root, text="▼ 折叠模组列表", command=self.toggle_mod_list,
                                      relief=tk.FLAT, bd=0, pady=2, padx=5, anchor='w')
        self.collapse_btn.grid(row=1, column=0, sticky='ew', padx=10, pady=(0,2))

        # ---------- 第2行：模组列表区域（可折叠） ----------
        self.list_frame = tk.LabelFrame(root, text="模组列表（勾选要翻译的模组）", padx=10, pady=10)
        self.list_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=(0,10))

        self.list_frame.grid_rowconfigure(1, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.select_all_var = tk.BooleanVar(value=True)
        select_all_cb = tk.Checkbutton(self.list_frame, text="全选", variable=self.select_all_var,
                                       command=self.toggle_select_all)
        select_all_cb.grid(row=0, column=0, sticky='w', padx=5, pady=(0,5))

        inner_canvas = tk.Canvas(self.list_frame, borderwidth=0, highlightthickness=0)
        inner_scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=inner_canvas.yview)
        inner_canvas.configure(yscrollcommand=inner_scrollbar.set)
        inner_canvas.grid(row=1, column=0, sticky='nsew')
        inner_scrollbar.grid(row=1, column=1, sticky='ns')
        self._bind_mousewheel(inner_canvas)

        self.mod_list_frame = tk.Frame(inner_canvas)
        self.mod_list_frame.bind("<Configure>", lambda e: inner_canvas.configure(scrollregion=inner_canvas.bbox("all")))
        inner_canvas.create_window((0, 0), window=self.mod_list_frame, anchor="nw")

        self.mod_vars = {}
        self.mod_checkbuttons = {}

        # ---------- 第3行：翻译设置 ----------
        top_frame = tk.LabelFrame(root, text="翻译设置", padx=10, pady=10)
        top_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=5)

        tk.Label(top_frame, text="翻译引擎:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.engine_var = tk.StringVar(value=ENGINE_DISPLAY.get(CONFIG.get('engine', 'mymemory'), 'MyMemory'))
        engine_values = list(ENGINE_DISPLAY.values())
        engine_combo = ttk.Combobox(top_frame, textvariable=self.engine_var, state='readonly',
                                    values=engine_values, width=20)
        engine_combo.grid(row=0, column=1, padx=5, pady=5)
        engine_combo.bind('<<ComboboxSelected>>', self.on_engine_change)

        tk.Label(top_frame, text="目标语言:").grid(row=0, column=2, sticky='e', padx=5, pady=5)
        self.target_lang_var = tk.StringVar(value=CONFIG.get('target_lang', '简体中文'))
        lang_combo = ttk.Combobox(top_frame, textvariable=self.target_lang_var, state='readonly',
                                  values=list(LANGUAGES.keys()), width=15)
        lang_combo.grid(row=0, column=3, padx=5, pady=5)

        # ---------- 第4行：配置容器 ----------
        self.config_container = tk.Frame(root)
        self.config_container.grid(row=4, column=0, sticky='ew', padx=10, pady=5)

        # MyMemory
        self.mymemory_frame = tk.LabelFrame(self.config_container, text="MyMemory 配置", padx=10, pady=10)
        self.mymemory_frame.pack(fill='x', pady=5)
        tk.Label(self.mymemory_frame, text="API Key:").grid(row=0, column=0, sticky='e', padx=5, pady=2)
        self.mymemory_api_key_var = tk.StringVar(value=CONFIG.get('mymemory_api_key', ''))
        tk.Entry(self.mymemory_frame, textvariable=self.mymemory_api_key_var, width=35, show='*').grid(row=0, column=1, padx=5)
        tk.Button(self.mymemory_frame, text="申请网址", command=lambda: webbrowser.open(API_URLS['mymemory'])).grid(row=0, column=2, padx=5)

        # OpenAI
        self.openai_frame = tk.LabelFrame(self.config_container, text="OpenAI 配置", padx=10, pady=10)
        self.openai_frame.pack(fill='x', pady=5)
        tk.Label(self.openai_frame, text="API Key:").grid(row=0, column=0, sticky='e', padx=5, pady=2)
        self.openai_api_key_var = tk.StringVar(value=CONFIG.get('openai_api_key', ''))
        tk.Entry(self.openai_frame, textvariable=self.openai_api_key_var, width=35, show='*').grid(row=0, column=1, padx=5)
        tk.Button(self.openai_frame, text="申请网址", command=lambda: webbrowser.open(API_URLS['openai'])).grid(row=0, column=2, padx=5)
        tk.Label(self.openai_frame, text="模型:").grid(row=1, column=0, sticky='e', padx=5, pady=2)
        self.openai_model_var = tk.StringVar(value=CONFIG.get('openai_model', 'gpt-4o-mini'))
        tk.Entry(self.openai_frame, textvariable=self.openai_model_var, width=35).grid(row=1, column=1, padx=5)

        # Claude
        self.claude_frame = tk.LabelFrame(self.config_container, text="Claude 配置", padx=10, pady=10)
        self.claude_frame.pack(fill='x', pady=5)
        tk.Label(self.claude_frame, text="API Key:").grid(row=0, column=0, sticky='e', padx=5, pady=2)
        self.claude_api_key_var = tk.StringVar(value=CONFIG.get('claude_api_key', ''))
        tk.Entry(self.claude_frame, textvariable=self.claude_api_key_var, width=35, show='*').grid(row=0, column=1, padx=5)
        tk.Button(self.claude_frame, text="申请网址", command=lambda: webbrowser.open(API_URLS['claude'])).grid(row=0, column=2, padx=5)
        tk.Label(self.claude_frame, text="模型:").grid(row=1, column=0, sticky='e', padx=5, pady=2)
        self.claude_model_var = tk.StringVar(value=CONFIG.get('claude_model', 'claude-3-5-haiku-20241022'))
        tk.Entry(self.claude_frame, textvariable=self.claude_model_var, width=35).grid(row=1, column=1, padx=5)

        # Gemini
        self.gemini_frame = tk.LabelFrame(self.config_container, text="Gemini 配置", padx=10, pady=10)
        self.gemini_frame.pack(fill='x', pady=5)
        tk.Label(self.gemini_frame, text="API Key:").grid(row=0, column=0, sticky='e', padx=5, pady=2)
        self.gemini_api_key_var = tk.StringVar(value=CONFIG.get('gemini_api_key', ''))
        tk.Entry(self.gemini_frame, textvariable=self.gemini_api_key_var, width=35, show='*').grid(row=0, column=1, padx=5)
        tk.Button(self.gemini_frame, text="申请网址", command=lambda: webbrowser.open(API_URLS['gemini'])).grid(row=0, column=2, padx=5)
        tk.Label(self.gemini_frame, text="模型:").grid(row=1, column=0, sticky='e', padx=5, pady=2)
        self.gemini_model_var = tk.StringVar(value=CONFIG.get('gemini_model', 'gemini-1.5-flash'))
        tk.Entry(self.gemini_frame, textvariable=self.gemini_model_var, width=35).grid(row=1, column=1, padx=5)

        # DeepSeek
        self.deepseek_frame = tk.LabelFrame(self.config_container, text="DeepSeek 配置", padx=10, pady=10)
        self.deepseek_frame.pack(fill='x', pady=5)
        tk.Label(self.deepseek_frame, text="API Key:").grid(row=0, column=0, sticky='e', padx=5, pady=2)
        self.deepseek_api_key_var = tk.StringVar(value=CONFIG.get('deepseek_api_key', ''))
        tk.Entry(self.deepseek_frame, textvariable=self.deepseek_api_key_var, width=35, show='*').grid(row=0, column=1, padx=5)
        tk.Button(self.deepseek_frame, text="申请网址", command=lambda: webbrowser.open(API_URLS['deepseek'])).grid(row=0, column=2, padx=5)
        tk.Label(self.deepseek_frame, text="模型:").grid(row=1, column=0, sticky='e', padx=5, pady=2)
        self.deepseek_model_var = tk.StringVar(value=CONFIG.get('deepseek_model', 'deepseek-v4-flash'))
        tk.Entry(self.deepseek_frame, textvariable=self.deepseek_model_var, width=35).grid(row=1, column=1, padx=5)

        # 本地AI
        self.local_frame = tk.LabelFrame(self.config_container, text="本地 AI 配置（OpenAI 兼容）", padx=10, pady=10)
        self.local_frame.pack(fill='x', pady=5)
        tk.Label(self.local_frame, text="API地址:").grid(row=0, column=0, sticky='e', padx=5, pady=2)
        self.local_api_url_var = tk.StringVar(value=CONFIG.get('local_api_url', 'http://localhost:11434/v1/chat/completions'))
        tk.Entry(self.local_frame, textvariable=self.local_api_url_var, width=35).grid(row=0, column=1, padx=5)
        tk.Button(self.local_frame, text="文档", command=lambda: webbrowser.open(API_URLS['local'])).grid(row=0, column=2, padx=5)
        tk.Label(self.local_frame, text="模型:").grid(row=1, column=0, sticky='e', padx=5, pady=2)
        self.local_model_var = tk.StringVar(value=CONFIG.get('local_model', 'llama3'))
        tk.Entry(self.local_frame, textvariable=self.local_model_var, width=35).grid(row=1, column=1, padx=5)
        tk.Label(self.local_frame, text="API Key(可选):").grid(row=2, column=0, sticky='e', padx=5, pady=2)
        self.local_api_key_var = tk.StringVar(value=CONFIG.get('local_api_key', ''))
        tk.Entry(self.local_frame, textvariable=self.local_api_key_var, width=35, show='*').grid(row=2, column=1, padx=5)

        # ---------- 第5行：保存/重新加载按钮 ----------
        btn_frame = tk.Frame(root)
        btn_frame.grid(row=5, column=0, sticky='ew', padx=10, pady=5)
        tk.Button(btn_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="重新加载", command=self.load_config).pack(side=tk.LEFT, padx=5)

        # ---------- 第6行：开始翻译按钮 ----------
        self.start_btn = tk.Button(root, text="开始翻译选中的模组", command=self.start_batch_translation, height=2, width=20)
        self.start_btn.grid(row=6, column=0, pady=5)

        # ---------- 第7行：日志显示 ----------
        self.log_area = scrolledtext.ScrolledText(root, height=10)
        self.log_area.grid(row=7, column=0, sticky='nsew', padx=10, pady=(5,10))

        # ---------- 第8行：底部信息（版本、作者、警示） ----------
        bottom_frame = tk.Frame(root)
        bottom_frame.grid(row=8, column=0, pady=5)

        info_row = tk.Frame(bottom_frame)
        info_row.grid(row=0, column=0, sticky='ew')
        info_row.grid_columnconfigure(0, weight=1)

        version_label = tk.Label(info_row, text="版本 1.0.0", fg="#87CEFA")
        version_label.pack(side=tk.LEFT, padx=5)

        author_label = tk.Label(info_row, text="作者：DeepSeek&神尾家的小観鈴", fg="#87CEFA")
        author_label.pack(side=tk.LEFT, padx=5)

        warning_label = tk.Label(bottom_frame, text="AI 翻译仅供参考，请人工校对。开源软件，使用风险自负。",
                                 fg="red", font=("Arial", 9))
        warning_label.grid(row=1, column=0, pady=(2,0))

        # 初始化
        self.load_config()
        self.on_engine_change()

        # 启动后自动弹出警告
        self.root.after(200, self.show_startup_warning)

    # ------------------ 折叠/展开模组列表 ------------------
    def toggle_mod_list(self):
        if self.list_frame.winfo_ismapped():
            self.list_frame.grid_remove()
            self.root.grid_rowconfigure(2, weight=0)   # 取消权重，避免留白
            self.collapse_btn.config(text="▼ 展开模组列表")
        else:
            self.list_frame.grid()
            self.root.grid_rowconfigure(2, weight=1)   # 恢复权重
            self.collapse_btn.config(text="▼ 折叠模组列表")

    # ------------------ 模组列表方法 ------------------
    def add_files(self):
        files = filedialog.askopenfilenames(
            title="选择 JAR 文件",
            filetypes=[("JAR 文件", "*.jar"), ("所有文件", "*.*")]
        )
        for f in files:
            if f not in self.mod_vars:
                self._add_mod_to_list(f)

    def add_folder(self):
        folder = filedialog.askdirectory(title="选择包含 JAR 文件的文件夹")
        if folder:
            for root_dir, dirs, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith('.jar'):
                        full_path = os.path.join(root_dir, file)
                        if full_path not in self.mod_vars:
                            self._add_mod_to_list(full_path)

    def _add_mod_to_list(self, path):
        var = tk.BooleanVar(value=self.select_all_var.get())
        cb = tk.Checkbutton(self.mod_list_frame, text=os.path.basename(path), variable=var, anchor='w')
        cb.pack(fill='x', padx=5, pady=2)
        self.mod_vars[path] = var
        self.mod_checkbuttons[path] = cb

    def clear_list(self):
        for path, cb in self.mod_checkbuttons.items():
            cb.destroy()
        self.mod_vars.clear()
        self.mod_checkbuttons.clear()
    
    def _bind_mousewheel(self, canvas):
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def on_enter(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        def on_leave(event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        
        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)

    def toggle_select_all(self):
        state = self.select_all_var.get()
        for var in self.mod_vars.values():
            var.set(state)

    def get_selected_mods(self):
        selected = []
        for path, var in self.mod_vars.items():
            if var.get():
                selected.append(path)
        return selected

    # ------------------ 其他方法 ------------------
    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        self.root.update_idletasks()

    def on_engine_change(self, event=None):
        display_engine = self.engine_var.get()
        engine = ENGINE_DISPLAY_TO_ID.get(display_engine, display_engine)
        for frame in [self.mymemory_frame, self.openai_frame, self.claude_frame,
                      self.gemini_frame, self.deepseek_frame, self.local_frame]:
            frame.pack_forget()
        if engine == 'mymemory':
            self.mymemory_frame.pack(fill='x', pady=5)
        elif engine == 'openai':
            self.openai_frame.pack(fill='x', pady=5)
        elif engine == 'claude':
            self.claude_frame.pack(fill='x', pady=5)
        elif engine == 'gemini':
            self.gemini_frame.pack(fill='x', pady=5)
        elif engine == 'deepseek':
            self.deepseek_frame.pack(fill='x', pady=5)
        elif engine == 'local':
            self.local_frame.pack(fill='x', pady=5)

    def save_config(self):
        # 保存引擎标识符（转换为小写）
        display_engine = self.engine_var.get()
        CONFIG['engine'] = ENGINE_DISPLAY_TO_ID.get(display_engine, display_engine)
        CONFIG['target_lang'] = self.target_lang_var.get()
        CONFIG['mymemory_api_key'] = self.mymemory_api_key_var.get()
        CONFIG['openai_api_key'] = self.openai_api_key_var.get()
        CONFIG['openai_model'] = self.openai_model_var.get()
        CONFIG['claude_api_key'] = self.claude_api_key_var.get()
        CONFIG['claude_model'] = self.claude_model_var.get()
        CONFIG['gemini_api_key'] = self.gemini_api_key_var.get()
        CONFIG['gemini_model'] = self.gemini_model_var.get()
        CONFIG['deepseek_api_key'] = self.deepseek_api_key_var.get()
        CONFIG['deepseek_model'] = self.deepseek_model_var.get()
        CONFIG['local_api_url'] = self.local_api_url_var.get()
        CONFIG['local_model'] = self.local_model_var.get()
        CONFIG['local_api_key'] = self.local_api_key_var.get()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(CONFIG, f, ensure_ascii=False, indent=2)
            self.log("配置已保存到 config.json")
            messagebox.showinfo("提示", "配置保存成功！")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败：{e}")

    def load_config(self):
        global CONFIG
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                CONFIG.update(saved)
                self.log("已加载上次保存的配置。")
            except Exception as e:
                self.log(f"加载配置失败，使用默认配置：{e}")
        # 更新界面变量
        engine_id = CONFIG.get('engine', 'mymemory')
        self.engine_var.set(ENGINE_DISPLAY.get(engine_id, engine_id))
        self.target_lang_var.set(CONFIG.get('target_lang', '简体中文'))
        self.mymemory_api_key_var.set(CONFIG.get('mymemory_api_key', ''))
        self.openai_api_key_var.set(CONFIG.get('openai_api_key', ''))
        self.openai_model_var.set(CONFIG.get('openai_model', 'gpt-4o-mini'))
        self.claude_api_key_var.set(CONFIG.get('claude_api_key', ''))
        self.claude_model_var.set(CONFIG.get('claude_model', 'claude-3-5-haiku-20241022'))
        self.gemini_api_key_var.set(CONFIG.get('gemini_api_key', ''))
        self.gemini_model_var.set(CONFIG.get('gemini_model', 'gemini-1.5-flash'))
        self.deepseek_api_key_var.set(CONFIG.get('deepseek_api_key', ''))
        self.deepseek_model_var.set(CONFIG.get('deepseek_model', 'deepseek-v4-flash'))
        self.local_api_url_var.set(CONFIG.get('local_api_url', 'http://localhost:11434/v1/chat/completions'))
        self.local_model_var.set(CONFIG.get('local_model', 'llama3'))
        self.local_api_key_var.set(CONFIG.get('local_api_key', ''))
        self.on_engine_change()

    def show_startup_warning(self):
        messagebox.showwarning(
            "重要提示",
            "AI 翻译可能不准确，建议人工校对。本软件为开源项目，使用后果由用户自行承担。"
        )

    def start_batch_translation(self):
        selected = self.get_selected_mods()
        if not selected:
            messagebox.showwarning("提示", "请至少勾选一个模组！")
            return

        # 更新 CONFIG（将显示名称转换回标识符）
        display_engine = self.engine_var.get()
        CONFIG['engine'] = ENGINE_DISPLAY_TO_ID.get(display_engine, display_engine)
        CONFIG['target_lang'] = self.target_lang_var.get()
        CONFIG['mymemory_api_key'] = self.mymemory_api_key_var.get()
        CONFIG['openai_api_key'] = self.openai_api_key_var.get()
        CONFIG['openai_model'] = self.openai_model_var.get()
        CONFIG['claude_api_key'] = self.claude_api_key_var.get()
        CONFIG['claude_model'] = self.claude_model_var.get()
        CONFIG['gemini_api_key'] = self.gemini_api_key_var.get()
        CONFIG['gemini_model'] = self.gemini_model_var.get()
        CONFIG['deepseek_api_key'] = self.deepseek_api_key_var.get()
        CONFIG['deepseek_model'] = self.deepseek_model_var.get()
        CONFIG['local_api_url'] = self.local_api_url_var.get()
        CONFIG['local_model'] = self.local_model_var.get()
        CONFIG['local_api_key'] = self.local_api_key_var.get()

        engine = CONFIG['engine']
        # 验证必要的配置
        if engine == 'mymemory' and not CONFIG['mymemory_api_key']:
            messagebox.showerror("错误", "请先填写 MyMemory API Key！")
            return
        elif engine == 'openai' and not CONFIG['openai_api_key']:
            messagebox.showerror("错误", "请先填写 OpenAI API Key！")
            return
        elif engine == 'claude' and not CONFIG['claude_api_key']:
            messagebox.showerror("错误", "请先填写 Claude API Key！")
            return
        elif engine == 'gemini' and not CONFIG['gemini_api_key']:
            messagebox.showerror("错误", "请先填写 Gemini API Key！")
            return
        elif engine == 'deepseek' and not CONFIG['deepseek_api_key']:
            messagebox.showerror("错误", "请先填写 DeepSeek API Key！")
            return
        elif engine == 'local' and not CONFIG['local_api_url']:
            messagebox.showerror("错误", "请先填写本地 API 地址！")
            return

        self.start_btn.config(state='disabled')
        threading.Thread(target=self.batch_translate, args=(selected,), daemon=True).start()

    def batch_translate(self, files):
        total = len(files)
        success_count = 0
        skipped_count = 0
        error_count = 0
        for idx, jar_path in enumerate(files, 1):
            self.log(f"\n========== 处理第 {idx}/{total} 个文件: {os.path.basename(jar_path)} ==========")
            status = self.translate_jar(jar_path, show_popup=False)
            if status == 'success':
                success_count += 1
            elif status.startswith('skipped'):
                skipped_count += 1
            elif status == 'error':
                error_count += 1
        summary = f"批量处理完成：成功 {success_count} 个，跳过 {skipped_count} 个，失败 {error_count} 个。"
        self.log(summary)
        messagebox.showinfo("批量处理完成", summary)
        self.start_btn.config(state='normal')

    def translate_jar(self, jar_path, show_popup=True):
        try:
            self.log(f"开始处理: {jar_path}")
            if has_target_lang_file(jar_path, CONFIG.get('target_lang', '简体中文')):
                self.log("已存在目标语言文件，跳过此模组。")
                return 'skipped_has_target'

            lang_files = find_lang_files(jar_path)
            if not lang_files:
                self.log("未找到英文语言文件！")
                if show_popup:
                    messagebox.showinfo("完成", "未找到英文语言文件。")
                return 'skipped_no_en'

            target_lang = CONFIG.get('target_lang', '简体中文')
            engine = CONFIG.get('engine', 'mymemory')
            self.log(f"目标语言: {target_lang}，引擎: {engine}")

            translated_files = {}
            failed_keys = []
            failed_count = 0

            with zipfile.ZipFile(jar_path, 'r') as jar:
                for lang_file in lang_files:
                    self.log(f"处理语言文件: {lang_file}")
                    content = jar.read(lang_file)
                    is_json = lang_file.endswith('.json')
                    translations = parse_lang_content(content, is_json)
                    total = len(translations)
                    self.log(f"找到 {total} 个翻译键")

                    if engine == 'mymemory':
                        translated, batch_failed = self.translate_mymemory_batch(translations, target_lang)
                        failed_keys.extend(batch_failed)
                    else:
                        translated, batch_failed = self.translate_ai_batch(translations, target_lang, engine)
                        failed_keys.extend(batch_failed)

                    failed_count = len(failed_keys)
                    if failed_count > 10:
                        raise Exception(
                            f"翻译失败次数超过 10 次（当前 {failed_count} 次），已终止翻译。\n"
                            "可能原因：网络不稳定、API 密钥无效或配额用尽、目标语言不支持等。"
                        )

                    mc_code = LANGUAGES.get(target_lang, {}).get('mc', 'zh_cn')
                    new_file = lang_file.replace('en_us', mc_code)
                    translated_files[new_file] = generate_lang_file(translated, is_json)
                    self.log(f"已准备语言文件: {new_file}")

            self.log("正在将翻译文件写入原 JAR...")
            with zipfile.ZipFile(jar_path, 'r') as zin:
                items = [(item, zin.read(item.filename)) for item in zin.infolist()]
                for path, content in translated_files.items():
                    items = [(item, data) for item, data in items if item.filename != path]
                    new_info = zipfile.ZipInfo(path)
                    new_info.date_time = time.localtime()[:6]
                    new_info.compress_type = zipfile.ZIP_DEFLATED
                    items.append((new_info, content))

            with zipfile.ZipFile(jar_path, 'w') as zout:
                for item, data in items:
                    zout.writestr(item, data)

            if failed_keys:
                failed_list = "\n".join(f"• {k}" for k in failed_keys)
                self.log(f"翻译完成，但以下 {len(failed_keys)} 个条目未能翻译：\n{failed_list}")
                if show_popup:
                    messagebox.showwarning(
                        "部分翻译失败",
                        f"翻译完成，但有 {len(failed_keys)} 个条目未能翻译：\n{failed_list}"
                    )
            else:
                self.log("翻译完成！所有条目均已成功翻译。")
                if show_popup:
                    messagebox.showinfo("完成", "翻译完成！所有条目均已成功翻译。")
            return 'success'
        except Exception as e:
            self.log(f"发生错误: {e}")
            if show_popup:
                messagebox.showerror("错误", str(e))
            return 'error'
        finally:
            if show_popup:
                self.start_btn.config(state='normal')

    def translate_mymemory_batch(self, translations, target_lang):
        translated = {}
        failed = []
        total = len(translations)
        completed = 0
        lock = threading.Lock()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_key = {executor.submit(translate_value, v, target_lang): k for k, v in translations.items()}
            for future in concurrent.futures.as_completed(future_to_key):
                key = future_to_key[future]
                original_value = translations[key]
                try:
                    translated_value = future.result()
                    if original_value.strip() and translated_value == original_value:
                        failed.append(key)
                        self.log(f"  ⚠ 翻译失败: {key}")
                    translated[key] = translated_value
                except Exception as e:
                    failed.append(key)
                    translated[key] = original_value
                    self.log(f"  ⚠ 翻译异常: {key} ({e})")
                with lock:
                    completed += 1
                    self.log(f"  进度: {completed}/{total} 条")
        return translated, failed

    def translate_ai_batch(self, translations, target_lang, engine):
        batch_size = CONFIG.get('batch_size', 20)
        translated = {}
        failed = []

        keys = list(translations.keys())
        total_batches = (len(keys) + batch_size - 1) // batch_size
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(keys))
            batch_keys = keys[start_idx:end_idx]
            batch_dict = {k: translations[k] for k in batch_keys}
            self.log(f"  正在翻译第 {batch_idx+1}/{total_batches} 批，共 {len(batch_keys)} 条...")
            result, batch_failed = translate_batch_ai(batch_dict, target_lang, engine)
            if result is None:
                self.log(f"  批量请求失败，回退到逐条翻译...")
                for k in batch_keys:
                    translated[k] = translate_value(translations[k], target_lang)
                    if translations[k].strip() and translated[k] == translations[k]:
                        failed.append(k)
            else:
                for k in batch_keys:
                    if k in result:
                        translated[k] = result[k]
                        if translations[k].strip() and translated[k] == translations[k]:
                            failed.append(k)
                    else:
                        failed.append(k)
                        translated[k] = translations[k]
            batch_fail_count = len(batch_failed)
            self.log(f"  第 {batch_idx+1} 批完成，失败 {batch_fail_count} 条。")
        return translated, failed

# ------------------ 主程序入口 ------------------
if __name__ == '__main__':
    if DRAG_DROP_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = TranslatorApp(root)
    root.mainloop()