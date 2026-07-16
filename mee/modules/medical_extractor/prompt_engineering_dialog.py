"""
AI提示词工程生成对话框
为每个Excel列名生成智能提示词
"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import json


class PromptEngineeringDialog(QDialog):
    """AI提示词工程生成对话框 - 苹果简约风格"""
    def __init__(self, template_config, parent=None):
        super().__init__(parent)
        self.template_config = template_config
        self.prompts = {}  # 存储生成的提示词
        self.setWindowTitle('AI提示词工程')
        self.setMinimumSize(1500, 950)  # 增加窗口最小尺寸
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 标题
        title_layout = QHBoxLayout()
        title = QLabel('AI提示词工程')
        title.setFont(QFont('SF Pro Display', 24, QFont.Bold))
        title.setStyleSheet('color: #1e293b;')
        title_layout.addWidget(title)

        title_layout.addStretch()

        help_btn = QPushButton('帮助')
        help_btn.setMinimumWidth(80)
        help_btn.setMinimumHeight(36)
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.clicked.connect(self.show_help)
        title_layout.addWidget(help_btn)

        layout.addLayout(title_layout)

        # 说明
        info_label = QLabel('为每个字段定义详细的提取规则，AI将根据这些规则更精确地提取数据')
        info_label.setWordWrap(True)
        info_label.setStyleSheet('''
            color: #64748b;
            padding: 16px 20px;
            background-color: #f8fafc;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            font-size: 13px;
        ''')
        layout.addWidget(info_label)

        # 主分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：字段列表
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        field_label = QLabel('字段列表')
        field_label.setFont(QFont('Arial', 14, QFont.Bold))
        field_label.setStyleSheet('color: #1e293b; padding: 10px 0;')
        left_layout.addWidget(field_label)

        self.field_list = QListWidget()
        self.field_list.setMinimumWidth(300)  # 增加宽度
        self.field_list.setFont(QFont('Arial', 11))  # 设置字体
        self.field_list.currentRowChanged.connect(self.on_field_selected)
        left_layout.addWidget(self.field_list)

        # 快速操作
        quick_btn_layout = QVBoxLayout()
        quick_btn_layout.setSpacing(10)

        auto_generate_btn = QPushButton('自动生成全部')
        auto_generate_btn.setMinimumHeight(40)
        auto_generate_btn.setCursor(Qt.PointingHandCursor)
        auto_generate_btn.clicked.connect(self.auto_generate_all)
        quick_btn_layout.addWidget(auto_generate_btn)

        import_btn = QPushButton('导入配置')
        import_btn.setMinimumHeight(40)
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.clicked.connect(self.import_prompts)
        quick_btn_layout.addWidget(import_btn)

        export_btn = QPushButton('导出配置')
        export_btn.setMinimumHeight(40)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self.export_prompts)
        quick_btn_layout.addWidget(export_btn)

        left_layout.addLayout(quick_btn_layout)

        left_panel.setLayout(left_layout)
        splitter.addWidget(left_panel)

        # 右侧：提示词编辑器（添加滚动区域）
        right_panel = QWidget()
        right_main_layout = QVBoxLayout()
        right_main_layout.setContentsMargins(0, 0, 0, 0)
        right_main_layout.setSpacing(0)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 创建滚动内容容器
        scroll_content = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(16)

        # 字段信息
        info_group = QGroupBox('字段信息')
        info_form = QFormLayout()
        info_form.setSpacing(16)  # 增加间距
        info_form.setLabelAlignment(Qt.AlignLeft)
        info_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        info_form.setHorizontalSpacing(25)  # 增加水平间距

        # 字段名标签
        field_name_label = QLabel('字段名:')
        field_name_label.setFont(QFont('Arial', 12, QFont.Bold))
        self.current_field_label = QLabel('未选择')
        self.current_field_label.setFont(QFont('Arial', 12))
        self.current_field_label.setStyleSheet('color: #1e293b; padding: 5px;')
        self.current_field_label.setMinimumHeight(30)
        info_form.addRow(field_name_label, self.current_field_label)

        # 数据类型标签
        type_label = QLabel('数据类型:')
        type_label.setFont(QFont('Arial', 12, QFont.Bold))
        self.field_type_label = QLabel('文本')
        self.field_type_label.setFont(QFont('Arial', 12))
        self.field_type_label.setStyleSheet('color: #475569; padding: 5px;')
        self.field_type_label.setMinimumHeight(30)
        info_form.addRow(type_label, self.field_type_label)

        # 字段描述标签
        desc_label = QLabel('字段描述:')
        desc_label.setFont(QFont('Arial', 12, QFont.Bold))
        self.field_desc_label = QLabel('无')
        self.field_desc_label.setWordWrap(True)
        self.field_desc_label.setFont(QFont('Arial', 12))
        self.field_desc_label.setStyleSheet('color: #475569; padding: 5px;')
        self.field_desc_label.setMinimumHeight(30)
        info_form.addRow(desc_label, self.field_desc_label)

        info_group.setLayout(info_form)
        right_layout.addWidget(info_group)

        # 提示词编辑
        prompt_group = QGroupBox('提示词配置')
        prompt_layout = QVBoxLayout()
        prompt_layout.setSpacing(18)  # 增加间距

        # 同义词
        syn_label = QLabel('同义词（用逗号分隔）')
        syn_label.setFont(QFont('Arial', 12, QFont.Bold))
        syn_label.setStyleSheet('color: #475569; padding: 5px 0;')
        prompt_layout.addWidget(syn_label)
        self.synonyms_input = QLineEdit()
        self.synonyms_input.setPlaceholderText('例如：年龄,岁,周岁,Age')
        self.synonyms_input.setMinimumHeight(42)  # 增加高度
        self.synonyms_input.setFont(QFont('Arial', 11))
        prompt_layout.addWidget(self.synonyms_input)

        # 提取规则
        extract_label = QLabel('提取规则说明')
        extract_label.setFont(QFont('Arial', 12, QFont.Bold))
        extract_label.setStyleSheet('color: #475569; padding: 5px 0;')
        prompt_layout.addWidget(extract_label)
        self.extraction_rule_text = QTextEdit()
        self.extraction_rule_text.setPlaceholderText(
            '例如：\n'
            '- 从病历中查找"年龄"、"岁"等关键词\n'
            '- 提取紧跟其后的数字\n'
            '- 如果找到"XX岁"格式，提取XX部分\n'
            '- 如果没有明确标注，从出生日期推算'
        )
        self.extraction_rule_text.setMinimumHeight(160)  # 增加高度
        self.extraction_rule_text.setMaximumHeight(200)
        self.extraction_rule_text.setFont(QFont('Arial', 11))
        prompt_layout.addWidget(self.extraction_rule_text)

        # 数据验证规则
        valid_label = QLabel('数据验证规则')
        valid_label.setFont(QFont('Arial', 12, QFont.Bold))
        valid_label.setStyleSheet('color: #475569; padding: 5px 0;')
        prompt_layout.addWidget(valid_label)
        self.validation_rule_text = QTextEdit()
        self.validation_rule_text.setPlaceholderText(
            '例如：\n'
            '- 年龄必须是0-120之间的整数\n'
            '- 如果提取失败，填写-1\n'
            '- 不要包含"岁"等单位'
        )
        self.validation_rule_text.setMinimumHeight(120)  # 增加高度
        self.validation_rule_text.setMaximumHeight(140)
        self.validation_rule_text.setFont(QFont('Arial', 11))
        prompt_layout.addWidget(self.validation_rule_text)

        # 示例
        example_label = QLabel('提取示例')
        example_label.setFont(QFont('Arial', 12, QFont.Bold))
        example_label.setStyleSheet('color: #475569; padding: 10px 0 5px 0;')
        prompt_layout.addWidget(example_label)

        example_form = QFormLayout()
        example_form.setSpacing(14)
        example_form.setLabelAlignment(Qt.AlignLeft)
        example_form.setHorizontalSpacing(25)

        # 病历示例标签
        input_label = QLabel('病历示例:')
        input_label.setFont(QFont('Arial', 11, QFont.Bold))
        self.example_input = QLineEdit()
        self.example_input.setPlaceholderText('输入示例病历文本')
        self.example_input.setMinimumHeight(42)
        self.example_input.setFont(QFont('Arial', 11))
        example_form.addRow(input_label, self.example_input)

        # 期望结果标签
        output_label = QLabel('期望结果:')
        output_label.setFont(QFont('Arial', 11, QFont.Bold))
        self.example_output = QLineEdit()
        self.example_output.setPlaceholderText('期望提取结果')
        self.example_output.setMinimumHeight(42)
        self.example_output.setFont(QFont('Arial', 11))
        example_form.addRow(output_label, self.example_output)

        prompt_layout.addLayout(example_form)

        # 保存按钮
        save_prompt_btn = QPushButton('保存当前字段')
        save_prompt_btn.setMinimumHeight(44)
        save_prompt_btn.setFont(QFont('Arial', 11, QFont.Bold))
        save_prompt_btn.setCursor(Qt.PointingHandCursor)
        save_prompt_btn.clicked.connect(self.save_current_prompt)
        prompt_layout.addWidget(save_prompt_btn)

        prompt_group.setLayout(prompt_layout)
        right_layout.addWidget(prompt_group)

        # 预览生成的提示词
        preview_group = QGroupBox('提示词预览')
        preview_layout = QVBoxLayout()
        preview_layout.setSpacing(12)

        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setMinimumHeight(180)  # 增加高度
        self.prompt_preview.setMaximumHeight(220)
        self.prompt_preview.setFont(QFont('Arial', 11))
        preview_layout.addWidget(self.prompt_preview)

        refresh_preview_btn = QPushButton('刷新预览')
        refresh_preview_btn.setMinimumHeight(40)
        refresh_preview_btn.setFont(QFont('Arial', 11, QFont.Bold))
        refresh_preview_btn.setCursor(Qt.PointingHandCursor)
        refresh_preview_btn.clicked.connect(self.refresh_preview)
        preview_layout.addWidget(refresh_preview_btn)

        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)

        # 将内容设置到滚动容器中
        scroll_content.setLayout(right_layout)
        scroll_area.setWidget(scroll_content)

        # 将滚动区域添加到右侧主布局
        right_main_layout.addWidget(scroll_area)
        right_panel.setLayout(right_main_layout)

        splitter.addWidget(right_panel)

        splitter.setSizes([320, 1050])
        layout.addWidget(splitter)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        button_layout.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.setMinimumWidth(120)
        cancel_btn.setMinimumHeight(42)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        apply_btn = QPushButton('应用并关闭')
        apply_btn.setMinimumWidth(120)
        apply_btn.setMinimumHeight(42)
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self.accept)
        button_layout.addWidget(apply_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # 加载字段
        self.load_fields()

    def apply_styles(self):
        """应用苹果简约风格"""
        self.setStyleSheet("""""")
        # self.setStyleSheet("""
        #     QDialog {
        #         background-color: #f8fafc;
        #     }
        #
        #     QGroupBox {
        #         font-size: 15px;
        #         font-weight: 600;
        #         color: #1e293b;
        #         border: none;
        #         background-color: white;
        #         border-radius: 12px;
        #         padding: 20px;
        #         margin-top: 15px;
        #     }
        #
        #     QGroupBox::title {
        #         subcontrol-origin: margin;
        #         subcontrol-position: top left;
        #         padding: 0 10px;
        #         color: #667eea;
        #     }
        #
        #     QPushButton {
        #         background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        #             stop:0 #667eea, stop:1 #764ba2);
        #         color: white;
        #         border: none;
        #         border-radius: 8px;
        #         padding: 10px 20px;
        #         font-size: 13px;
        #         font-weight: 600;
        #     }
        #
        #     QPushButton:hover {
        #         background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        #             stop:0 #764ba2, stop:1 #667eea);
        #     }
        #
        #     QPushButton:pressed {
        #         background: #5a67d8;
        #     }
        #
        #     QLineEdit {
        #         background-color: white;
        #         border: 2px solid #e2e8f0;
        #         border-radius: 8px;
        #         padding: 10px 14px;
        #         font-size: 13px;
        #         color: #1e293b;
        #     }
        #
        #     QLineEdit:focus {
        #         border: 2px solid #667eea;
        #     }
        #
        #     QTextEdit {
        #         background-color: white;
        #         border: 2px solid #e2e8f0;
        #         border-radius: 8px;
        #         padding: 12px;
        #         font-size: 13px;
        #         color: #1e293b;
        #     }
        #
        #     QTextEdit:focus {
        #         border: 2px solid #667eea;
        #     }
        #
        #     QListWidget {
        #         background-color: white;
        #         border: 2px solid #e2e8f0;
        #         border-radius: 8px;
        #         padding: 8px;
        #         font-size: 13px;
        #     }
        #
        #     QListWidget::item {
        #         padding: 12px;
        #         border-radius: 6px;
        #         margin: 2px;
        #         color: #475569;
        #     }
        #
        #     QListWidget::item:selected {
        #         background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        #             stop:0 #667eea, stop:1 #764ba2);
        #         color: white;
        #     }
        #
        #     QListWidget::item:hover:!selected {
        #         background: #f1f5f9;
        #     }
        #
        #     QLabel {
        #         color: #475569;
        #     }
        #
        #     QFormLayout {
        #         spacing: 12px;
        #     }
        # """)

    def load_fields(self):
        """加载字段列表"""
        self.field_list.clear()
        fields = self.template_config.get('fields', [])

        for field in fields:
            column_name = field.get('column', '')
            self.field_list.addItem(column_name)

    def on_field_selected(self, index):
        """字段选中"""
        if index < 0:
            return

        fields = self.template_config.get('fields', [])
        if index >= len(fields):
            return

        field = fields[index]
        column_name = field.get('column', '')
        field_type = field.get('type', '文本')
        field_desc = field.get('description', '无')

        # 更新字段信息
        self.current_field_label.setText(column_name)
        self.field_type_label.setText(field_type)
        self.field_desc_label.setText(field_desc if field_desc else '无')

        # 加载已保存的提示词（如果有）
        if column_name in self.prompts:
            prompt_data = self.prompts[column_name]
            self.synonyms_input.setText(prompt_data.get('synonyms', ''))
            self.extraction_rule_text.setPlainText(prompt_data.get('extraction_rule', ''))
            self.validation_rule_text.setPlainText(prompt_data.get('validation_rule', ''))
            self.example_input.setText(prompt_data.get('example_input', ''))
            self.example_output.setText(prompt_data.get('example_output', ''))
        else:
            # 清空
            self.synonyms_input.clear()
            self.extraction_rule_text.clear()
            self.validation_rule_text.clear()
            self.example_input.clear()
            self.example_output.clear()

            # 自动生成初始提示词
            self.auto_generate_for_field(column_name, field_type, field_desc)

        self.refresh_preview()

    def auto_generate_for_field(self, column_name, field_type, field_desc):
        """为单个字段自动生成提示词"""
        # 智能生成同义词
        synonyms = self.generate_synonyms(column_name)
        self.synonyms_input.setText(synonyms)

        # 生成提取规则
        extraction_rule = self.generate_extraction_rule(column_name, field_type, field_desc)
        self.extraction_rule_text.setPlainText(extraction_rule)

        # 生成验证规则
        validation_rule = self.generate_validation_rule(column_name, field_type)
        self.validation_rule_text.setPlainText(validation_rule)

    def generate_synonyms(self, column_name) -> str:
        """智能生成同义词"""
        # 常见医疗字段的同义词映射
        synonym_dict = {
            '姓名': '姓名,名字,患者姓名,病人姓名,Name',
            '年龄': '年龄,岁,周岁,Age',
            '性别': '性别,男女,Gender,Sex',
            '身高': '身高,身长,Height,Ht',
            '体重': '体重,体质量,Weight,Wt',
            '血压': '血压,BP,Blood Pressure',
            '心率': '心率,HR,Heart Rate,脉搏',
            '体温': '体温,T,Temperature',
            '主诉': '主诉,Chief Complaint,CC',
            '现病史': '现病史,HPI,Present Illness',
            '既往史': '既往史,Past History',
            '诊断': '诊断,Diagnosis,Dx',
            '治疗': '治疗,Treatment,Therapy',
        }

        # 查找匹配
        for key in synonym_dict:
            if key in column_name:
                return synonym_dict[key]

        # 默认使用列名本身
        return column_name

    def generate_extraction_rule(self, column_name, field_type, field_desc) -> str:
        """生成提取规则"""
        rules = []

        rules.append(f"1. 在病历中搜索包含 \"{column_name}\" 或其同义词的片段")

        if field_type in ['数字', '整数', '小数']:
            rules.append("2. 提取紧跟关键词后的数字部分")
            rules.append("3. 忽略单位，只提取纯数字")
            rules.append("4. 如果有多个数值，提取最相关的一个")
        elif field_type == '日期':
            rules.append("2. 识别日期格式：YYYY-MM-DD, YYYY/MM/DD, YYYY年MM月DD日")
            rules.append("3. 统一转换为 YYYY-MM-DD 格式")
        else:
            rules.append("2. 提取关键词后的描述性文本")
            rules.append("3. 保留原始表述，不要过度简化")

        rules.append("5. 如果完全没有提及该信息，填写 -1")

        if field_desc:
            rules.append(f"6. 特别注意：{field_desc}")

        return '\n'.join(rules)

    def generate_validation_rule(self, column_name, field_type) -> str:
        """生成验证规则"""
        rules = []

        if field_type in ['数字', '整数']:
            rules.append("- 必须是整数")
            rules.append("- 不包含单位和符号")

            if '年龄' in column_name:
                rules.append("- 范围：0-120")
            elif '血压' in column_name:
                rules.append("- 范围：50-250")
            elif '心率' in column_name:
                rules.append("- 范围：30-200")

        elif field_type in ['小数', '浮点数']:
            rules.append("- 可以包含小数点")
            rules.append("- 不包含单位")

        elif field_type == '日期':
            rules.append("- 格式：YYYY-MM-DD")
            rules.append("- 年份：1900-2100")

        else:
            rules.append("- 文本类型，保持原样")
            rules.append("- 不要包含换行符")

        rules.append("- 如果提取失败或未提及，填写 -1")

        return '\n'.join(rules)

    def save_current_prompt(self):
        """保存当前字段的提示词"""
        index = self.field_list.currentRow()
        if index < 0:
            return

        fields = self.template_config.get('fields', [])
        if index >= len(fields):
            return

        column_name = fields[index].get('column', '')

        # 保存提示词数据
        self.prompts[column_name] = {
            'synonyms': self.synonyms_input.text(),
            'extraction_rule': self.extraction_rule_text.toPlainText(),
            'validation_rule': self.validation_rule_text.toPlainText(),
            'example_input': self.example_input.text(),
            'example_output': self.example_output.text()
        }

        QMessageBox.information(self, '成功', f'✅ 已保存 "{column_name}" 的提示词配置')
        self.refresh_preview()

    def refresh_preview(self):
        """刷新预览"""
        index = self.field_list.currentRow()
        if index < 0:
            return

        fields = self.template_config.get('fields', [])
        if index >= len(fields):
            return

        column_name = fields[index].get('column', '')

        # 构建完整提示词
        preview_text = f"""字段：{column_name}

同义词：
{self.synonyms_input.text()}

提取规则：
{self.extraction_rule_text.toPlainText()}

验证规则：
{self.validation_rule_text.toPlainText()}

---
这些规则将被集成到AI提示词中，指导AI更精确地提取该字段的数据。
"""
        self.prompt_preview.setPlainText(preview_text)

    def auto_generate_all(self):
        """自动生成所有字段的提示词"""
        fields = self.template_config.get('fields', [])

        reply = QMessageBox.question(
            self, '确认',
            f'将为 {len(fields)} 个字段自动生成提示词，是否继续？',
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            for field in fields:
                column_name = field.get('column', '')
                field_type = field.get('type', '文本')
                field_desc = field.get('description', '')

                # 生成同义词
                synonyms = self.generate_synonyms(column_name)

                # 生成规则
                extraction_rule = self.generate_extraction_rule(column_name, field_type, field_desc)
                validation_rule = self.generate_validation_rule(column_name, field_type)

                # 保存
                self.prompts[column_name] = {
                    'synonyms': synonyms,
                    'extraction_rule': extraction_rule,
                    'validation_rule': validation_rule,
                    'example_input': '',
                    'example_output': ''
                }

            QMessageBox.information(self, '成功', f'✅ 已为所有 {len(fields)} 个字段生成提示词')

    def import_prompts(self):
        """导入提示词配置"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, '导入提示词配置', '', 'JSON Files (*.json)'
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.prompts = json.load(f)
                QMessageBox.information(self, '成功', '✅ 提示词配置已导入')
            except Exception as e:
                QMessageBox.warning(self, '错误', f'导入失败:\n{str(e)}')

    def export_prompts(self):
        """导出提示词配置"""
        if not self.prompts:
            QMessageBox.warning(self, '提示', '没有可导出的提示词配置')
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, '导出提示词配置', 'prompt_config.json', 'JSON Files (*.json)'
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.prompts, f, indent=4, ensure_ascii=False)
                QMessageBox.information(self, '成功', f'✅ 提示词配置已导出到:\n{file_path}')
            except Exception as e:
                QMessageBox.warning(self, '错误', f'导出失败:\n{str(e)}')

    def show_help(self):
        """显示帮助"""
        help_text = """
        <h3>🤖 AI提示词工程 - 使用说明</h3>

        <h4>什么是提示词工程？</h4>
        <p>提示词工程是通过为每个字段定义详细的提取规则，帮助AI更准确地理解和提取数据。</p>

        <h4>主要功能：</h4>
        <ul>
            <li><b>同义词：</b>定义字段的各种表达方式，帮助AI识别</li>
            <li><b>提取规则：</b>告诉AI如何从病历中找到并提取该字段</li>
            <li><b>验证规则：</b>定义数据的合法范围和格式</li>
            <li><b>示例：</b>提供示例帮助AI学习</li>
        </ul>

        <h4>使用步骤：</h4>
        <ol>
            <li>点击左侧字段列表选择字段</li>
            <li>编辑或使用自动生成的提示词</li>
            <li>点击"保存当前字段提示词"</li>
            <li>重复以上步骤完成所有字段</li>
            <li>或直接点击"自动生成所有提示词"</li>
            <li>点击"应用并关闭"</li>
        </ol>

        <h4>提示：</h4>
        <p>详细的提示词可以显著提高提取准确率，建议为重要字段手动优化！</p>
        """

        msg = QMessageBox(self)
        msg.setWindowTitle('帮助')
        msg.setTextFormat(Qt.RichText)
        msg.setText(help_text)
        msg.exec_()

    def get_prompts(self):
        """获取所有提示词配置"""
        return self.prompts
