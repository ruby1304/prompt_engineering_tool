# ui/components/forms.py
import streamlit as st

# ui/components/forms.py 中添加 template_form 组件
def template_form(template=None, on_save=None, key_prefix=""):
    """模板编辑表单
    
    Args:
        template: 现有模板数据
        on_save: 保存回调函数
        key_prefix: 组件键前缀
    
    Returns:
        dict or None: 更新后的模板数据或None（如果未保存）
    """
    if template is None or not isinstance(template, dict):
        template = {
            "name": "",
            "description": "",
            "template": "",
            "variables": {}
        }
    
    # 确保变量是有效的字典
    if "variables" not in template or not isinstance(template["variables"], dict):
        template["variables"] = {}

    template = template or {
        "name": "",
        "description": "",
        "template": "",
        "variables": {}
    }
    
    with st.form(key=f"{key_prefix}_template_form"):
        st.subheader("基本信息")
        
        name = st.text_input(
            "模板名称", 
            value=template.get("name", ""), 
            key=f"{key_prefix}_name",
            help="给模板起一个描述性的名称"
        )
        
        description = st.text_area(
            "模板描述", 
            value=template.get("description", ""), 
            key=f"{key_prefix}_desc",
            help="描述此模板的用途和适用场景"
        )
        
        st.subheader("模板内容")
        
        template_content = st.text_area(
            "提示词模板", 
            value=template.get("template", ""), 
            height=300, 
            key=f"{key_prefix}_content",
            help="在模板中使用 {{变量名}} 标记变量"
        )
        
        # 变量编辑器
        st.subheader("变量设置")
        st.markdown("使用`{{变量名}}`在模板中标记变量")
        
        variables = template.get("variables", {}).copy()
        
        # 添加新变量
        col1, col2 = st.columns([3, 1])
        with col1:
            new_var = st.text_input(
                "变量名称", 
                key=f"{key_prefix}_new_var",
                help="输入新变量名称，然后点击添加"
            )
        with col2:
            add_var = st.form_submit_button("添加变量")
        
        if add_var and new_var and new_var not in variables:
            variables[new_var] = {"description": "", "default": ""}
        
        # 现有变量编辑
        if variables:
            st.markdown("### 编辑现有变量")
            
            # 创建变量编辑区域
            for i, (var_name, var_config) in enumerate(list(variables.items())):
                with st.expander(f"变量: {var_name}", expanded=i==0):
                    var_desc = st.text_input(
                        "描述", 
                        value=var_config.get("description", ""), 
                        key=f"{key_prefix}_var_{var_name}_desc",
                        help="变量的说明文字"
                    )
                    
                    var_default = st.text_input(
                        "默认值", 
                        value=var_config.get("default", ""), 
                        key=f"{key_prefix}_var_{var_name}_default",
                        help="变量的默认值"
                    )
                    
                    # 删除变量按钮
                    if st.checkbox(f"删除此变量", key=f"{key_prefix}_var_{var_name}_delete"):
                        # 标记为删除，实际在保存时处理
                        st.session_state[f"{key_prefix}_delete_var_{var_name}"] = True
                    
                    # 更新变量配置
                    variables[var_name] = {
                        "description": var_desc,
                        "default": var_default
                    }
        
        # 移除标记为删除的变量
        for var_name in list(variables.keys()):
            if st.session_state.get(f"{key_prefix}_delete_var_{var_name}", False):
                del variables[var_name]
                # 清除会话状态中的标记
                if f"{key_prefix}_delete_var_{var_name}" in st.session_state:
                    del st.session_state[f"{key_prefix}_delete_var_{var_name}"]
        
        # 更新模板数据
        updated_template = {
            "name": name,
            "description": description,
            "template": template_content,
            "variables": variables
        }
        
        # 提交按钮
        submit = st.form_submit_button("保存模板")

        # 如果提交并且提供了回调
        if submit:
            if on_save:
                try:
                    success = on_save(updated_template)
                    if success:
                        st.success("模板已保存！")
                except Exception as e:
                    st.error(f"保存模板时出错: {str(e)}")
            return updated_template
        
        return None

def api_key_form(label, current_key, on_save, key_prefix, help_text=None):
    """API密钥表单组件
    
    Args:
        label: 表单标签
        current_key: 当前密钥值
        on_save: 保存回调函数
        key_prefix: 组件键前缀
        help_text: 帮助文本
    
    Returns:
        bool: 是否保存成功
    """
    new_key = st.text_input(
        label,
        value=current_key,
        type="password",
        help=help_text,
        key=f"{key_prefix}_key_input"
    )
    
    if st.button(f"保存{label}", key=f"{key_prefix}_save_btn"):
        if on_save:
            on_save(new_key)
        return True
    
    return False


def test_set_form(test_set=None, on_save=None, key_prefix=""):
    """测试集编辑表单
    
    Args:
        test_set: 现有测试集数据
        on_save: 保存回调函数
        key_prefix: 组件键前缀
    
    Returns:
        dict or None: 更新后的测试集数据或None（如果未保存）
    """
    test_set = test_set or {
        "name": "",
        "description": "",
        "variables": {},
        "cases": []
    }
    
    with st.form(key=f"{key_prefix}_test_set_form"):
        st.subheader("基本信息")
        
        name = st.text_input(
            "测试集名称", 
            value=test_set.get("name", ""), 
            key=f"{key_prefix}_name",
            help="给测试集起一个描述性的名称"
        )
        
        description = st.text_area(
            "测试集描述", 
            value=test_set.get("description", ""), 
            key=f"{key_prefix}_desc",
            help="描述此测试集的用途和测试范围"
        )
        
        # 测试集变量编辑（可选功能）
        with st.expander("测试集全局变量（可选）", expanded=False):
            st.markdown("全局变量会应用到所有测试用例")
            
            variables = test_set.get("variables", {}).copy()
            
            # 添加新变量
            col1, col2 = st.columns([3, 1])
            with col1:
                new_var = st.text_input(
                    "变量名称", 
                    key=f"{key_prefix}_new_var",
                    help="输入新变量名称，然后点击添加"
                )
            
            with col2:
                add_var = st.form_submit_button("添加变量")
            
            if add_var and new_var and new_var not in variables:
                variables[new_var] = ""
            
            # 现有变量编辑
            if variables:
                st.markdown("### 编辑现有变量")
                
                # 创建变量编辑区域
                for var_name, var_value in list(variables.items()):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        var_value = st.text_input(
                            f"变量 {var_name}", 
                            value=var_value, 
                            key=f"{key_prefix}_var_{var_name}"
                        )
                        variables[var_name] = var_value
                    
                    with col2:
                        if st.checkbox(f"删除", key=f"{key_prefix}_var_{var_name}_delete"):
                            # 标记为删除，实际在保存时处理
                            st.session_state[f"{key_prefix}_delete_var_{var_name}"] = True
            
            # 移除标记为删除的变量
            for var_name in list(variables.keys()):
                if st.session_state.get(f"{key_prefix}_delete_var_{var_name}", False):
                    del variables[var_name]
                    # 清除会话状态中的标记
                    if f"{key_prefix}_delete_var_{var_name}" in st.session_state:
                        del st.session_state[f"{key_prefix}_delete_var_{var_name}"]
        
        # 测试集统计信息
        st.markdown("### 测试集统计")
        st.markdown(f"当前测试用例数: {len(test_set.get('cases', []))}")
        
        # 更新测试集数据
        updated_test_set = {
            "name": name,
            "description": description,
            "variables": variables,
            "cases": test_set.get("cases", [])
        }
        
        # 提交按钮
        submit = st.form_submit_button("保存测试集")
        
        # 如果提交并且提供了回调
        if submit:
            if on_save:
                success = on_save(updated_test_set)
                if success:
                    st.success("测试集已保存！")
            return updated_test_set
        
        return None

def test_case_form(test_case=None, on_save=None, on_delete=None, key_prefix=""):
    """测试用例编辑表单
    
    Args:
        test_case: 现有测试用例数据
        on_save: 保存回调函数
        on_delete: 删除回调函数
        key_prefix: 组件键前缀
    
    Returns:
        dict or None: 更新后的测试用例数据或None（如果未保存）
    """
    test_case = test_case or {
        "id": "new_case",
        "description": "",
        "variables": {},
        "user_input": "",
        "expected_output": "",
        "evaluation_criteria": {}
    }
    
    with st.form(key=f"{key_prefix}_test_case_form"):
        # 基本信息
        col1, col2 = st.columns([1, 3])
        
        with col1:
            case_id = st.text_input(
                "用例ID", 
                value=test_case.get("id", ""), 
                key=f"{key_prefix}_id",
                disabled=True,  # ID不可编辑
                help="系统自动生成的唯一标识符"
            )
        
        with col2:
            description = st.text_input(
                "用例描述", 
                value=test_case.get("description", ""), 
                key=f"{key_prefix}_desc",
                help="简短描述此测试用例的目的"
            )
        
        # 用户输入
        st.subheader("用户输入")
        user_input = st.text_area(
            "输入内容", 
            value=test_case.get("user_input", ""), 
            height=150,
            key=f"{key_prefix}_input",
            help="模拟用户向AI提出的问题或请求"
        )
        
        # 期望输出
        st.subheader("期望输出")
        expected_output = st.text_area(
            "期望输出", 
            value=test_case.get("expected_output", ""), 
            height=200,
            key=f"{key_prefix}_output",
            help="模型应该生成的理想响应，用于评估实际输出的质量"
        )
        
        # 评估标准
        st.subheader("评估标准")
        st.markdown("设置评估模型响应的标准，每项标准对应一个评分维度")
        
        criteria = test_case.get("evaluation_criteria", {}).copy()
        
        # 添加新标准
        col1, col2 = st.columns([3, 1])
        with col1:
            new_criterion = st.text_input(
                "标准名称", 
                key=f"{key_prefix}_new_criterion",
                help="输入新评估标准名称，如：准确性、完整性等"
            )
        
        with col2:
            add_criterion = st.form_submit_button("添加标准")
        
        if add_criterion and new_criterion and new_criterion not in criteria:
            criteria[new_criterion] = "评估说明"
        
        # 现有标准编辑
        if criteria:
            for criterion, description in list(criteria.items()):
                col1, col2, col3 = st.columns([2, 3, 1])
                
                with col1:
                    st.markdown(f"**{criterion}**")
                
                with col2:
                    criterion_desc = st.text_input(
                        "说明", 
                        value=description, 
                        key=f"{key_prefix}_criterion_{criterion}",
                        help="描述此评估标准的具体要求"
                    )
                    criteria[criterion] = criterion_desc
                
                with col3:
                    if st.checkbox("删除", key=f"{key_prefix}_criterion_{criterion}_delete"):
                        # 标记为删除
                        st.session_state[f"{key_prefix}_delete_criterion_{criterion}"] = True
        else:
            st.info("请添加至少一项评估标准")
        
        # 移除标记为删除的标准
        for criterion in list(criteria.keys()):
            if st.session_state.get(f"{key_prefix}_delete_criterion_{criterion}", False):
                del criteria[criterion]
                # 清除会话状态中的标记
                if f"{key_prefix}_delete_criterion_{criterion}" in st.session_state:
                    del st.session_state[f"{key_prefix}_delete_criterion_{criterion}"]
        
        # 测试用例特定变量（可选）
        with st.expander("用例特定变量（可选）", expanded=False):
            st.markdown("这些变量仅适用于此测试用例，会覆盖测试集全局变量")
            
            variables = test_case.get("variables", {}).copy()
            
            # 添加新变量
            col1, col2 = st.columns([3, 1])
            with col1:
                case_new_var = st.text_input(
                    "变量名称", 
                    key=f"{key_prefix}_case_new_var",
                    help="输入新变量名称，然后点击添加"
                )
            
            with col2:
                case_add_var = st.form_submit_button("添加变量")
            
            if case_add_var and case_new_var and case_new_var not in variables:
                variables[case_new_var] = ""
            
            # 现有变量编辑
            if variables:
                for var_name, var_value in list(variables.items()):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        var_value = st.text_input(
                            f"变量 {var_name}", 
                            value=var_value, 
                            key=f"{key_prefix}_case_var_{var_name}"
                        )
                        variables[var_name] = var_value
                    
                    with col2:
                        if st.checkbox(f"删除", key=f"{key_prefix}_case_var_{var_name}_delete"):
                            # 标记为删除
                            st.session_state[f"{key_prefix}_delete_case_var_{var_name}"] = True
            
            # 移除标记为删除的变量
            for var_name in list(variables.keys()):
                if st.session_state.get(f"{key_prefix}_delete_case_var_{var_name}", False):
                    del variables[var_name]
                    # 清除会话状态中的标记
                    if f"{key_prefix}_delete_case_var_{var_name}" in st.session_state:
                        del st.session_state[f"{key_prefix}_delete_case_var_{var_name}"]
        
        # 更新测试用例数据
        updated_test_case = {
            "id": case_id,
            "description": description,
            "variables": variables,
            "user_input": user_input,
            "expected_output": expected_output,
            "evaluation_criteria": criteria
        }
        
        # 提交按钮
        col1, col2 = st.columns([3, 1])
        with col1:
            submit = st.form_submit_button("保存测试用例")
        
        # 如果提交并且提供了回调
        if submit:
            if on_save:
                success = on_save(updated_test_case)
                if success:
                    st.success("测试用例已保存！")
            return updated_test_case
        
        # 删除按钮（在表单外部）
        return None

# 在表单外部添加删除按钮
def test_case_delete_button(case_id, on_delete=None, key_prefix=""):
    """测试用例删除按钮
    
    Args:
        case_id: 要删除的测试用例ID
        on_delete: 删除回调函数
        key_prefix: 组件键前缀
    
    Returns:
        bool: 是否删除成功
    """
    delete_confirm = st.checkbox(
        "我确认要删除此测试用例", 
        key=f"{key_prefix}_delete_confirm"
    )
    
    if delete_confirm:
        if st.button("删除测试用例", key=f"{key_prefix}_delete_btn", type="primary"):
            if on_delete:
                success = on_delete(case_id)
                if success:
                    st.success(f"测试用例 {case_id} 已删除！")
                    return True
    
    return False


def test_config_form(on_start=None, key_prefix=""):
    """测试配置表单
    
    Args:
        on_start: 开始测试的回调函数
        key_prefix: 组件键前缀
    
    Returns:
        dict or None: 测试配置或None
    """
    with st.form(key=f"{key_prefix}_test_config_form"):
        st.subheader("模型参数")
        
        col1, col2 = st.columns(2)
        
        with col1:
            temperature = st.slider(
                "Temperature", 
                min_value=0.0, 
                max_value=1.0, 
                value=0.7, 
                step=0.1,
                help="控制输出的随机性",
                key=f"{key_prefix}_temperature"
            )
        
        with col2:
            max_tokens = st.number_input(
                "最大输出Token数", 
                min_value=1, 
                max_value=4096, 
                value=1024,
                help="限制模型响应的最大长度",
                key=f"{key_prefix}_max_tokens"
            )
        
        # 添加测试运行次数配置
        num_runs = st.number_input(
            "每个配置运行次数", 
            min_value=1, 
            max_value=10, 
            value=1,
            help="每个模型-模板-测试用例组合运行的次数",
            key=f"{key_prefix}_num_runs"
        )
        
        st.subheader("评估选项")
        
        run_evaluation = st.checkbox(
            "自动评估响应", 
            value=True,
            help="使用评估模型对生成的响应进行评分",
            key=f"{key_prefix}_run_eval"
        )
        
        if run_evaluation:
            # 获取所有可用模型
            available_models = get_available_models()
            all_models = []
            
            # 创建统一的模型列表，包含提供商信息
            for provider, models in available_models.items():
                for model in models:
                    all_models.append((provider, model))
            
            # 创建格式化的选项列表，显示提供商信息
            model_options = [f"{model} ({provider})" for provider, model in all_models]
            model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
            
            # 如果没有可用模型，显示提示
            if not model_options:
                st.warning("未找到可用模型，无法执行评估")
                evaluator_model = None
                evaluator_provider = None
            else:
                evaluator_model_option = st.selectbox(
                    "评估模型", 
                    model_options,
                    key=f"{key_prefix}_eval_model"
                )
                
                if evaluator_model_option:
                    evaluator_model, evaluator_provider = model_map[evaluator_model_option]
                else:
                    evaluator_model = None
                    evaluator_provider = None
        else:
            evaluator_model = None
            evaluator_provider = None
        
        # 提交按钮
        submit = st.form_submit_button("开始测试", type="primary")
        
        if submit:
            # 创建测试配置
            config = {
                "params": {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "num_runs": num_runs  # 添加运行次数
                },
                "evaluation": {
                    "run": run_evaluation,
                    "model": evaluator_model,
                    "provider": evaluator_provider
                },
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
            }
            
            # 调用开始测试回调
            if on_start:
                on_start(config)
            
            return config
        
        return None