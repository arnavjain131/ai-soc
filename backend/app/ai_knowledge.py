"""Bounded retrieval from a reviewed, repository-owned knowledge library.

No uploads, arbitrary paths, network access, model calls or workspace data.
"""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Rule = Literal['brute_force_v1', 'password_spray_v1', 'tcp_port_scan_v1', 'suricata_priority_alert_v1']
SOURCES = frozenset((
    'https://attack.mitre.org/techniques/T1110/001/',
    'https://attack.mitre.org/techniques/T1110/003/',
    'https://attack.mitre.org/techniques/T1046/',
    'https://docs.suricata.io/en/suricata-7.0.3/output/eve/eve-json-output.html',
))
METHOD = 'local-keyword-v1'


class Section(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{2,60}$')
    title: str = Field(min_length=1, max_length=120)
    keywords: tuple[str, ...] = Field(min_length=1, max_length=20)
    guidance: str = Field(min_length=30, max_length=1200)


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{2,60}$')
    title: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r'^[0-9]{1,5}$')
    rules: tuple[Rule, ...] = Field(max_length=4)
    source_url: str | None
    sections: tuple[Section, ...] = Field(min_length=1, max_length=8)


class Library(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}\.\d+$')
    documents: tuple[Document, ...] = Field(min_length=1, max_length=16)


def parse_library(raw):
    if len(raw) > 65536:
        raise ValueError('Approved knowledge library exceeds its size bound')
    library = Library.model_validate_json(raw)
    ids = [doc.id for doc in library.documents]
    section_ids = [section.id for doc in library.documents for section in doc.sections]
    if len(set(ids)) != len(ids) or len(set(section_ids)) != len(section_ids):
        raise ValueError('Approved knowledge identifiers must be unique')
    if any(doc.source_url is not None and doc.source_url not in SOURCES for doc in library.documents):
        raise ValueError('Knowledge source URL is not approved')
    if len(section_ids) > 64:
        raise ValueError('Approved knowledge library exceeds its section bound')
    return library


@lru_cache(maxsize=1)
def library():
    # This exact path is part of the release. Do not discover files from uploads
    # or accept a path, URL, workspace note or event payload from an API caller.
    try:
        return parse_library((Path(__file__).parent / 'knowledge' / 'approved.json').read_bytes())
    except (OSError, ValueError):
        raise ValueError('Approved knowledge library is unavailable or invalid') from None


def knowledge_info():
    data = library()
    canonical = data.model_dump_json().encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return {'version':data.version + '-' + digest[:12], 'method':METHOD,
            'document_count':len(data.documents),
            'section_count':sum(len(doc.sections) for doc in data.documents)}


def retrieve(rule_keys, question=None, limit=3):
    """Rules gate eligibility; lexical overlap ranks eligible sections.

    Unknown questions can return no additional guidance. Scores are internal
    ranking values, never security confidence. Stable IDs break score ties.
    """
    limit = max(0, min(3, limit))
    if not limit:
        return []
    tokens = set(re.findall(r'[a-z]{3,}', (question or '').lower()))
    stop = {'the','this','that','does','was','were','why','how','what','with','from','and','for','incident'}
    tokens -= stop
    candidates = []
    for doc in library().documents:
        if doc.rules and not set(doc.rules).intersection(rule_keys):
            continue
        for section in doc.sections:
            keywords = set(section.keywords)
            title = set(re.findall(r'[a-z]{3,}',section.title.lower()))
            score = len(tokens & keywords)*4 + len(tokens & title)*2
            if question is None:
                score = 2 if doc.rules else 1
            if not score:
                continue
            candidates.append((score,doc,section))
    candidates.sort(key=lambda item:(-item[0],item[2].id))
    return [{'id':'kb.'+section.id, 'title':doc.title+' — '+section.title,
             'url':doc.source_url, 'guidance':section.guidance,
             'document_id':doc.id, 'section':section.title, 'version':doc.version,
             'content_hash':hashlib.sha256(section.guidance.encode()).hexdigest(),
             'kind':'approved_procedure'}
            for _,doc,section in candidates[:limit]]


def ground_references(context):
    """Refresh retrieval for summaries and stored questions alike."""
    base = [ref for ref in context['references'] if not ref['id'].startswith('kb.')]
    selected = retrieve(context['rule_keys'],context.get('analyst_question'),limit=4-len(base))
    info = knowledge_info()
    return {**context,'references':base+selected,'knowledge_version':info['version'],
            'retrieval':{**info,'selected_sections':len(selected)}}
