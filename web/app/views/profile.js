/* 个人信息配置（报告人姓名 / 部门）。
 *
 * 这一页是**交付版新增**的：需求报告里"报告人取当前登录用户、不可改"，
 * 但本期没有登录（范围外），所以原先只能写死在配置里 —— 交付给客户后
 * 每台设备都得能填自己的名字，否则导出的报告署名全是开发者的。
 *
 * 设计上刻意做成**单页两字段**：
 *  - 只有一个表单页，没有列表、没有历史 —— 它就是一个设置项；
 *  - 保存后回「我的」，卡片上立刻能看到新署名（用户能当场确认写进去了）；
 *  - 已保存的报告**不受影响**（报告里存的是当时的快照，见 repo/defects.js）。
 */

import { PROFILE_LIMITS, profileLabel } from '../product.js';
import { pathFor } from '../router.js';
import * as profileRepo from '../repo/profile.js';
import { flash } from '../ui/dialog.js';
import { clearFieldErrors, collectFields, showFieldErrors } from '../ui/form.js';
import { h } from '../ui/dom.js';
import { actionBar, backLink, card, formRow, input, pageHead } from './layout.js';

const FORM_ID = 'profile-form';
const FIELDS = ['reporter_name', 'reporter_department'];

export async function form(ctx) {
    const current = await profileRepo.read(ctx.db);

    const build = (values) => h('form', { id: FORM_ID, novalidate: true }, [
        h('div.form-table', null, [
            formRow({
                label: '报告人姓名',
                forId: 'reporter_name',
                required: true,
                control: input({
                    name: 'reporter_name', value: values.reporter_name,
                    maxlength: PROFILE_LIMITS.reporter_name, placeholder: '如：张三',
                }),
                hint: '会写进缺陷报告详情与 Word 附页的「报告人」一栏',
            }),
            formRow({
                label: '部门',
                forId: 'reporter_department',
                required: true,
                control: input({
                    name: 'reporter_department', value: values.reporter_department,
                    maxlength: PROFILE_LIMITS.reporter_department, placeholder: '如：检测部',
                }),
                hint: '与姓名合成「姓名（部门）」一起显示',
            }),
        ]),
        h('p.hint', {
            text: '只影响之后新填写的缺陷报告；已经保存的报告里存的是当时的署名，不会被改动。'
                + '这项设置保存在本机浏览器里，不随备份文件迁移。',
        }),
    ]);

    const form = build(current);

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        clearFieldErrors(form);
        const { data, errors } = profileRepo.parseForm(collectFields(form, FIELDS));
        if (Object.keys(errors).length) {
            showFieldErrors(form, errors);
            return;
        }
        try {
            const saved = await profileRepo.save(ctx.db, data);
            flash(`个人信息已保存：${profileLabel(saved)}`);
            ctx.navigate(pathFor('me.index'));
        } catch (error) {
            flash(`保存失败：${error.message}`, 'error');
        }
    });

    return {
        chrome: 'form',
        nodes: [
            card([
                ...pageHead('个人信息配置', backLink(pathFor('me.index'), '返回我的')),
                h('p.sub', { text: '这里填写的名字会成为之后所有缺陷报告的报告人署名' }),
                form,
            ], 'form-card'),
            actionBar({ cancelHref: pathFor('me.index'), cancelLabel: '取消', submitLabel: '保存', formId: FORM_ID }),
        ],
    };
}
