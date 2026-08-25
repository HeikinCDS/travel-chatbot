"""Normalize supported Malay and Chinese travel requests into English NLP text.

JomVoyage keeps one well-tested English intent and entity pipeline.  This
module provides a deterministic, offline vocabulary layer for the prototype's
Malay and Simplified Chinese interfaces so common travel requests reach that
same pipeline without requiring a translation API.
"""

from __future__ import annotations

import re


SUPPORTED_INPUT_LANGUAGES = {"en", "ms", "zh"}


MALAY_PHRASES = (
    ("tunjukkan lebih banyak pilihan", "show me more options"),
    ("tunjukkan pilihan lain", "show me different options"),
    ("kembali ke pilihan sebelumnya", "show the previous options"),
    ("mulakan perbualan baru", "start over"),
    ("padam pilihan perjalanan", "clear my preferences"),
    ("tiada keperluan khas", "no special accessibility requirements"),
    ("mesra warga emas", "elderly friendly"),
    ("mesra kerusi roda", "wheelchair accessible"),
    ("akses kerusi roda", "wheelchair access"),
    ("tandas orang kurang upaya", "accessible toilet"),
    ("tandas oku", "accessible toilet"),
    ("tempat duduk berdekatan", "benches and places to rest"),
    ("berjalan kaki minimum", "minimal walking"),
    ("tidak banyak berjalan", "minimal walking"),
    ("tanpa tangga", "step free"),
    ("warga emas", "elderly"),
    ("ibu bapa saya", "my parents"),
    ("alam semula jadi", "nature"),
    ("hidupan liar", "wildlife"),
    ("taman tema", "theme park"),
    ("mata air panas", "hot spring"),
    ("paling murah", "cheapest"),
    ("akses paling mudah", "easiest access"),
    ("lawatan paling singkat", "shortest visit"),
    ("ceritakan tentang", "tell me about"),
    ("maklumat tentang", "information about"),
    ("saya mahu melawat", "I want to visit"),
    ("saya ingin melawat", "I would like to visit"),
    ("saya mahu pergi ke", "I want to visit"),
    ("cadangkan", "recommend"),
    ("syorkan", "recommend"),
    ("tarikan", "attraction"),
    ("tempat", "place"),
    ("pantai", "beach"),
    ("sejarah", "history"),
    ("warisan", "heritage"),
    ("budaya", "culture"),
    ("muzium", "museum"),
    ("makanan", "food"),
    ("membeli-belah", "shopping"),
    ("pengembaraan", "adventure"),
    ("santai", "relaxation"),
    ("tenang", "peaceful"),
    ("percuma", "free entry"),
    ("bajet", "budget"),
    ("bawah", "under"),
    ("di", "in"),
)


CHINESE_PHRASES = (
    ("显示更多选择", "show me more options"),
    ("查看更多选择", "show me more options"),
    ("给我更多选择", "give me more options"),
    ("显示其他选择", "show me different options"),
    ("返回之前的选择", "show the previous options"),
    ("重新开始", "start over"),
    ("清除旅行偏好", "clear my preferences"),
    ("没有特殊需求", "no special accessibility requirements"),
    ("无障碍厕所", "accessible toilet"),
    ("轮椅无障碍", "wheelchair accessible"),
    ("轮椅通道", "wheelchair access"),
    ("少走路", "minimal walking"),
    ("休息座椅", "benches and places to rest"),
    ("没有楼梯", "step free"),
    ("适合长者", "suitable for elderly"),
    ("适合老人", "suitable for elderly"),
    ("老年人", "elderly"),
    ("长者", "elderly"),
    ("我的父母", "my parents"),
    ("自然景点", "nature attraction"),
    ("野生动物", "wildlife"),
    ("主题公园", "theme park"),
    ("温泉", "hot spring"),
    ("最便宜", "cheapest"),
    ("最容易到达", "easiest access"),
    ("最短行程", "shortest visit"),
    ("告诉我关于", "tell me about"),
    ("介绍一下", "tell me about"),
    ("我想去", "I want to visit"),
    ("我想参观", "I want to visit"),
    ("推荐", "recommend"),
    ("景点", "attraction"),
    ("地方", "place"),
    ("大自然", "nature"),
    ("自然", "nature"),
    ("海滩", "beach"),
    ("历史", "history"),
    ("文化", "culture"),
    ("博物馆", "museum"),
    ("美食", "food"),
    ("购物", "shopping"),
    ("探险", "adventure"),
    ("放松", "relaxation"),
    ("宁静", "peaceful"),
    ("免费", "free entry"),
    ("预算", "budget"),
    ("以下", "under"),
    ("在", "in"),
    ("的", " "),
)


CHINESE_STATES = (
    ("森美兰", "Negeri Sembilan"),
    ("吉隆坡", "Kuala Lumpur"),
    ("布城", "Putrajaya"),
    ("纳闽", "Labuan"),
    ("槟城", "Penang"),
    ("柔佛", "Johor"),
    ("吉打", "Kedah"),
    ("吉兰丹", "Kelantan"),
    ("马六甲", "Melaka"),
    ("彭亨", "Pahang"),
    ("霹雳", "Perak"),
    ("玻璃市", "Perlis"),
    ("沙巴", "Sabah"),
    ("砂拉越", "Sarawak"),
    ("雪兰莪", "Selangor"),
    ("登嘉楼", "Terengganu"),
)


def _replace_malay(text: str) -> str:
    normalized = text
    for source, target in MALAY_PHRASES:
        normalized = re.sub(
            rf"(?<!\w){re.escape(source)}(?!\w)",
            target,
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


def _replace_chinese(text: str) -> str:
    normalized = text
    for source, target in CHINESE_STATES + CHINESE_PHRASES:
        normalized = normalized.replace(source, f" {target} ")
    return normalized


def normalize_user_input(text: str, language: str = "en") -> str:
    """Return English-normalized NLP text for a supported interface language."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if language not in SUPPORTED_INPUT_LANGUAGES:
        raise ValueError("unsupported input language")
    if language == "en":
        return text.strip()

    normalized = _replace_malay(text) if language == "ms" else _replace_chinese(text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized
