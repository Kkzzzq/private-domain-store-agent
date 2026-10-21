window.AssistantPresentation = (() => {
  const label = '(?:参考资料|参考来源|引用来源|资料来源|数据来源|信息来源|知识来源|检索来源|来源|Sources?|References?)';
  const file = '[A-Za-z0-9_.\\-/\\\\]+\\.(?:md|txt|pdf|json|ya?ml|py|js|tsx?|csv|sql)(?:#[\\w-]+)?';
  const terms = [['知识库','店铺资料'],['关键词检索','查询'],['语义检索','查询'],['向量检索','查询'],['向量索引','店铺资料'],['检索','查询']];
  function clean(text) {
    const value=String(text??'').replace(/\r\n/g,'\n'), output=[];
    let sourceBlock=false,citation=new RegExp(file,'i').test(value);
    for(let line of value.split('\n')) {
      const plain=line.replace(/^\s*(?:#{1,6}\s*|>\s*|[-*+]\s+|\d+[.)]\s+)/,'').replaceAll('**','').trim();
      if(new RegExp('^'+label+'\\s*(?:[（(][^）)\\n]*[）)])?\\s*(?:[:：].*)?$','i').test(plain)){sourceBlock=true;citation=true;continue;}
      const entry=new RegExp(file,'i').test(plain)||/^(?:\[\^?\d+\]:|https?:\/\/|\[[^\]]+\]\(https?:\/\/)/.test(plain);
      if(sourceBlock&&(!plain||entry))continue;
      sourceBlock=false;
      line=line.replace(new RegExp('[（(]\\s*'+label+'\\s*(?:[:：]|[（(])[^\\n]*?[）)]','gi'),'');
      line=line.replace(new RegExp('【[^】\\n]*'+file+'[^】\\n]*】','gi'),'');
      line=line.replace(new RegExp('(?<![\\w\\u4e00-\\u9fff])'+label+'\\s*(?:[（(][^）)\\n]*[）)])?\\s*[:：][^\\n]*','gi'),'');
      line=line.replace(/\[[^\]\n]*\]\([^\s)]*\.(?:md|txt|pdf|json|ya?ml|py|js|tsx?|csv|sql)(?:#[^)]*)?\)/gi,'');
      line=line.replace(new RegExp(file,'gi'),'店铺规则');
      if(citation)line=line.replace(/\[\^?\d+\]/g,'');
      for(const [term,replacement]of terms)line=line.replaceAll(term,replacement);
      output.push(line.trimEnd());
    }
    return output.join('\n').replace(/\n{3,}/g,'\n\n').trim()||'请告诉我您想了解的具体问题，我来帮您确认。';
  }
  return {clean};
})();
