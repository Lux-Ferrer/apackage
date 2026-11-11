/* 表单的公共小工具：取值、就地标红、清除标记。
 *
 * 与 Flask 侧"服务端校验失败回填"同语义：**错误信息出现在出错的字段旁边**，
 * 而不是攒成一坨放在页首 —— 手机上那是最容易被键盘挡住的位置。
 *
 * 视图层各自写过一份（projects / records / reports），新页面（个人信息配置）用这里的；
 * 老页面暂时保留各自的实现，改动它们对交付没有收益，反而多一份回归风险。
 */

import { h } from './dom.js';

/** 按名字取出表单值（缺字段 → 空串，调用方不必到处判空）。 */
export function collectFields(form, names) {
    const data = {};
    for (const name of names) {
        const field = form.querySelector(`[name="${name}"]`);
        data[name] = field ? field.value : '';
    }
    return data;
}

/** 把 `{字段名: 错误文案}` 就地标到字段上，并把焦点移到第一个出错的字段。 */
export function showFieldErrors(form, errors) {
    for (const [name, message] of Object.entries(errors)) {
        const field = form.querySelector(`[name="${name}"]`);
        if (!field) continue;
        field.classList.add('input-error');
        const holder = field.closest('.form-control') ?? field.parentNode;
        let box = holder.querySelector('.field-error');
        if (!box) {
            box = h('p.field-error');
            holder.appendChild(box);
        }
        box.textContent = message;
    }
    const first = form.querySelector('.input-error');
    if (first) first.focus();
    return errors;
}

/** 清除上一轮的错误标记（每次提交前调用，否则会残留旧提示）。 */
export function clearFieldErrors(form) {
    form.querySelectorAll('.input-error').forEach((element) => element.classList.remove('input-error'));
    form.querySelectorAll('.field-error').forEach((element) => element.remove());
}
