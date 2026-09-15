from app.core.paths import PROJECT_ROOT
from app.core.logger import logger  # 可选，加日志更友好
import string


def _required_placeholders(raw_prompt: str) -> set:
    """
    解析模板中真实存在的占位符名集合。

    用 string.Formatter 而非正则：它会正确跳过 {{ }} 转义出来的字面大括号
    （提示词里输出 JSON 示例时会用到转义），并支持 {a[0]} / {a.b} 这类形式——
    这里只取根字段名，便于与 kwargs 的键做集合比对。
    """
    names = set()
    for _, field_name, _, _ in string.Formatter().parse(raw_prompt):
        if field_name:
            names.add(field_name.split("[")[0].split(".")[0])
    return names


def load_prompt(name: str, **kwargs) -> str:
    """
    加载提示词并渲染变量占位符
    :param name: 提示词文件名（不带.prompt后缀，如image_summary）
    :param **kwargs: 需渲染的变量键值对（如root_folder="测试文件", image_content=("上文内容", "下文内容")）
    :return: 渲染后的最终提示词字符串
    """
    # 1. 拼接提示词路径（你的原有逻辑，完全保留）
    prompt_path = PROJECT_ROOT / 'prompts' / f'{name}.prompt'

    # 2. 校验文件是否存在（可选，避免文件不存在直接报错）
    if not prompt_path.exists():
        raise FileNotFoundError(f"提示词文件不存在：{prompt_path.absolute()}")

    # 3. 读取纯文本提示词（你的原有逻辑）
    raw_prompt = prompt_path.read_text(encoding='utf-8')

    # 4. 核心：如果传了参数，渲染占位符；没传参，直接返回原文本
    if kwargs:
        # 4.1 完备性检查：把"裸 KeyError"变成带明细的可诊断异常。
        required = _required_placeholders(raw_prompt)
        provided = set(kwargs.keys())
        missing = required - provided
        if missing:
            raise ValueError(
                f"提示词 {name}.prompt 占位符缺失：需要 {sorted(required)}，"
                f"实际提供 {sorted(provided)}，缺少 {sorted(missing)}"
            )
        # 4.2 渲染
        rendered_prompt = raw_prompt.format(**kwargs)
        logger.debug(f"提示词渲染成功，替换变量：{list(kwargs.keys())}")
        return rendered_prompt
    return raw_prompt



if __name__ == '__main__':
    # 测试：传入参数渲染占位符（和业务代码中实际使用方式一致）
    root_folder = "hl3070使用说明书"  # 要替换的文件名称
    image_content = ("这是图片的上文内容", "这是图片的下文内容")  # 要替换的上下文
    # 调用时传入所有需要渲染的变量（键名必须和.prompt中的占位符完全一致）
    final_prompt = load_prompt(
        name='image_summary',
        root_folder=root_folder,  # 对应{root_folder}
        image_content=image_content  # 对应{image_content[0]}、{image_content[1]}
    )
    print("✅ 渲染后的最终提示词：")
    print(final_prompt)