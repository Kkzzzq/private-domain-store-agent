/* 报告标题以登记用例名称为准；时间与编号退居次要位置，避免只看到一串时间戳而认不出报告内容。 */
window.OPReportName = (() => {
  const rows = value => Array.isArray(value) ? value : [];
  const clock = value => value ? new Date(/[Z+]|\d-\d\d:\d\d$/.test(value) ? value : value + 'Z')
    .toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'}) : '';
  function titleOf(run, id, catalog) {
    const snapshot = rows(run?.target?.case_snapshots).find(row => row?.id === id);
    if (snapshot?.title) return snapshot.title;
    const result = rows(run?.results).find(row => row?.id === id);
    if (result?.doc?.title) return result.doc.title;
    const entry = rows(catalog).find(row => row?.id === id);
    return entry?.title || entry?.doc?.title || '';
  }
  /* 用例名称列表，保留 id 便于对照报告；名称缺失时退回 id，绝不显示空白。 */
  function cases(run, catalog) {
    return rows(run?.results).map(row => ({id: row.id, title: titleOf(run, row.id, catalog) || row.id, status: row.status}));
  }
  function brief(run, catalog, limit = 3) {
    const items = cases(run, catalog);
    if (!items.length) return '无用例记录';
    const head = items.slice(0, limit).map(item => item.title).join('、');
    return items.length > limit ? `${head} 等 ${items.length} 条用例` : head;
  }
  /* 报告列表、下拉框与标题统一使用；时间/编号只作为次要参考。 */
  function label(run, catalog, {status = '', time = false} = {}) {
    if (!run) return '未选择报告';
    const parts = [brief(run, catalog)];
    if (status) parts.push(status);
    if (time) { const stamp = clock(run.created_at || run.started_at); if (stamp) parts.push(stamp); }
    parts.push(`报告 ${String(run.id || '').slice(0, 6) || '未记录'}`);
    return parts.join(' · ');
  }
  function ids(run) { return rows(run?.results).map(row => row.id).join('、'); }
  return {titleOf, cases, brief, label, ids};
})();