import { useState } from 'react';
import type { OnlineCatalog } from '../types';
import Icon from './Icon';

interface Props {
  catalog: OnlineCatalog | null;
  locked: boolean;
  onSearch: (query: string, page: number) => void;
  onDownload: (id: string) => void;
  onLibrary: () => void;
}

export default function OnlinePage({ catalog, locked, onSearch, onDownload, onLibrary }: Props) {
  const [query, setQuery] = useState(catalog?.query ?? '');
  return <div className="online-page">
    <header className="page-heading"><div><h1>在线乐谱</h1><p>来自 RocoMusic 洛克乐谱，下载后即可离线演奏。</p></div>
      <button className="button secondary" onClick={onLibrary}>我的谱库 <Icon name="arrow" size={16} /></button></header>
    <form className="online-search" onSubmit={(event) => { event.preventDefault(); if (!locked) onSearch(query, 1); }}>
      <label className="search-box"><Icon name="search" size={18} /><input aria-label="搜索在线乐谱" placeholder="搜索曲名、作者…" maxLength={100} value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <button className="button primary" disabled={locked} type="submit">搜索</button>
      <button className="button secondary" disabled={locked} type="button" onClick={() => { setQuery(''); onSearch('', 1); }}>浏览最新</button>
    </form>
    <p className="online-hint">保留下载原谱，按当前九键映射导入；不会自动演奏。播放期间请先停止再下载。</p>
    {!catalog ? <section className="panel online-empty"><Icon name="library" size={32} /><h2>发现下一首想弹的旋律</h2><p>输入关键词，或点击“浏览最新”。加载失败可直接重试。</p></section> : <>
      <div className="online-results" aria-live="polite">第 {catalog.page} 页 · {catalog.items.length} 首{catalog.query ? ` · “${catalog.query}”` : ' · 最新分享'}</div>
      {catalog.items.length === 0 ? <section className="panel online-empty"><h2>没有找到匹配的曲谱</h2><p>试试更短的曲名或作者名。</p></section> : <div className="online-grid">{catalog.items.map((item) =>
        <article className="panel online-card" key={item.id}>
          <div className="online-card-top"><span className="online-art"><Icon name="music" size={25} /></span><span className="count-pill">{item.format || '曲谱'}</span></div>
          <h2 title={item.title}>{item.title}</h2><p>{item.subtitle || '社区分享曲谱'}</p><small>制谱 / 分享：{item.author || '社区作者'}</small>
          <button className="button primary" disabled={locked || item.format.toUpperCase() !== 'MIDI'} onClick={() => onDownload(item.id)}><Icon name="import" size={16} />{item.format.toUpperCase() === 'MIDI' ? '下载到我的谱库' : '暂不支持此格式'}</button>
        </article>)}</div>}
      <nav className="online-pagination" aria-label="在线谱库翻页"><button className="button secondary" disabled={locked || catalog.page <= 1} onClick={() => onSearch(catalog.query, catalog.page - 1)}>上一页</button><span>{catalog.page}</span><button className="button secondary" disabled={locked || !catalog.has_next} onClick={() => onSearch(catalog.query, catalog.page + 1)}>下一页</button></nav>
    </>}
  </div>;
}
