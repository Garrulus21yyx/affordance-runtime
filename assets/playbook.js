(() => {
 const select = document.querySelector('#scenario');
 const host = document.querySelector('#transition-demo');
 const boundary = document.querySelector('#demo-boundary');
 if (!select || !host || !boundary) return;
 const scenarios = {
  effect: {world:'当前仍是列表页；预期弹窗未出现。',result:'dispatch = sent\n局部后置条件 = unsatisfied\n页面语义未改变',monitor:'单次无效果是反馈证据。是否触发循环，要结合既有转移记录。',note:'发送成功不等于效果成功；ActionPolicy 应依据当前页面重审，Monitor 不臆测按钮业务语义。'},
  repeat: {world:'列表内容与已读记录保持不变。',result:'读取返回已见信息；再次点击仍无预期效果。',monitor:'首次重复 → 下一次决策注入恢复信号。\n无进展的替代读取加入同一 failure center；再次进入成员 → control_stalled。',note:'换工具名称不会自动解除停滞。控制终止也不等于任务成功或业务上不可完成。'},
  escape: {world:'页面可以保持不变，但已展开此前未交付的完整记录。',result:'InformationDelta = NEW_INFORMATION\n保留新记录字段和来源范围',monitor:'owner 证明新信息 → 解除原 failure center。\n同一 ActionPolicy 根据新证据选择动作。',note:'没有 GUI 变化也可能获得新信息；是否推进用户目标仍由模型结合 TaskGoal 判断。'}
 };
 function render(){const s=scenarios[select.value];host.replaceChildren();[['fresh World',s.world],['ToolResult / transition',s.result],['Monitor feedback',s.monitor]].forEach(([title,text])=>{const card=document.createElement('article');card.className='card';const h=document.createElement('h3');h.textContent=title;const p=document.createElement('p');p.textContent=text;card.append(h,p);host.append(card);});boundary.textContent=s.note;}
 select.addEventListener('change',render);render();
})();
