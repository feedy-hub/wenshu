"""Supported translation languages and shared prompt wording."""

DEFAULT_SOURCE = '英语'
DEFAULT_TARGET = '简体中文'
AUTO_SOURCE = '自动识别'
LANGUAGES = (
    {'value': '简体中文', 'label': '简体中文', 'tag': 'zh-Hans', 'name': 'Simplified Chinese', 'direction': 'ltr'},
    {'value': '繁体中文', 'label': '繁體中文', 'tag': 'zh-Hant', 'name': 'Traditional Chinese', 'direction': 'ltr'},
    {'value': '英语', 'label': '英语 English', 'tag': 'en', 'name': 'English', 'direction': 'ltr'},
    {'value': '日语', 'label': '日语 日本語', 'tag': 'ja', 'name': 'Japanese', 'direction': 'ltr'},
    {'value': '韩语', 'label': '韩语 한국어', 'tag': 'ko', 'name': 'Korean', 'direction': 'ltr'},
    {'value': '法语', 'label': '法语 Français', 'tag': 'fr', 'name': 'French', 'direction': 'ltr'},
    {'value': '德语', 'label': '德语 Deutsch', 'tag': 'de', 'name': 'German', 'direction': 'ltr'},
    {'value': '西班牙语', 'label': '西班牙语 Español', 'tag': 'es', 'name': 'Spanish', 'direction': 'ltr'},
    {'value': '葡萄牙语', 'label': '葡萄牙语 Português', 'tag': 'pt', 'name': 'Portuguese', 'direction': 'ltr'},
    {'value': '意大利语', 'label': '意大利语 Italiano', 'tag': 'it', 'name': 'Italian', 'direction': 'ltr'},
    {'value': '俄语', 'label': '俄语 Русский', 'tag': 'ru', 'name': 'Russian', 'direction': 'ltr'},
    {'value': '阿拉伯语', 'label': '阿拉伯语 العربية', 'tag': 'ar', 'name': 'Arabic', 'direction': 'rtl'},
    {'value': '印地语', 'label': '印地语 हिन्दी', 'tag': 'hi', 'name': 'Hindi', 'direction': 'ltr'},
)
BY_VALUE = {language['value']: language for language in LANGUAGES}


def validate_pair(source, target):
    if not isinstance(source, str) or source not in (*BY_VALUE, AUTO_SOURCE):
        raise ValueError('请选择支持的原文语言。')
    if not isinstance(target, str) or target not in BY_VALUE:
        raise ValueError('请选择支持的译文语言。')
    if source == target:
        raise ValueError('原文语言和译文语言不能相同。')
    return source, target


def name(value):
    return BY_VALUE.get(value, {}).get('name', value)


def translation_instruction(config):
    source = config.get('source', DEFAULT_SOURCE)
    target = name(config.get('target', DEFAULT_TARGET))
    if source == AUTO_SOURCE:
        return f'Detect the source language and translate the supplied academic text into {target}. '
    return f'Translate the supplied academic text from {name(source)} into {target}. '
