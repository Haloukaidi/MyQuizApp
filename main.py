# --- 模拟手机屏幕尺寸 ---
from kivy.config import Config

Config.set('graphics', 'width', '400')
Config.set('graphics', 'height', '800')
# -------------------------

import os
import json
import glob
import random
from datetime import datetime
from bs4 import BeautifulSoup

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.properties import ObjectProperty, StringProperty, ListProperty, BooleanProperty,OptionProperty
from kivy.clock import Clock
from kivy.utils import get_color_from_hex

# --- 数据和逻辑代码 (无修改) ---
RECORDS_FILE = 'quiz_data.json'


def load_data():
    if not os.path.exists(RECORDS_FILE): return {'in_progress': {}, 'completed': []}
    try:
        with open(RECORDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {'in_progress': {}, 'completed': []}


def save_data(data):
    with open(RECORDS_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)


def delete_all_records():
    if os.path.exists(RECORDS_FILE): os.remove(RECORDS_FILE); return True
    return False


def extract_questions_from_html(file_path):
    if not os.path.exists(file_path): return None
    with open(file_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, 'html.parser')
    all_questions_data = []
    question_containers = soup.find_all('div', class_='test_content_nr')
    for container in question_containers:
        title_div = container.find_previous('div', class_='test_content_title')
        if not title_div or not title_div.find('h2'): continue
        question_type = title_div.find('h2').get_text(strip=True)
        if question_type not in ["单选题", "多选题", "判断题"]: continue
        questions_in_section = container.find_all('li', id=lambda x: x and x.startswith('qu_'))
        for question_item in questions_in_section:
            question_id = question_item.get('id')
            question_text_element = question_item.find('div', class_='test_content_nr_tt').find('font')
            if question_text_element and question_text_element.find('i'): question_text_element.find('i').decompose()
            question_text = question_text_element.get_text(strip=True) if question_text_element else ""
            options = {}
            option_elements = question_item.find_all('li', class_='option')
            for option in option_elements:
                label = option.find('label')
                if label:
                    option_raw_text = label.get_text(strip=True)
                    option_value_p = label.find('p', class_='ue')
                    if option_value_p:
                        option_key = option_raw_text.split('.')[0].strip();
                        option_value = option_value_p.get_text(strip=True)
                        options[option_key] = option_value
                    elif "对" in option_raw_text or "错" in option_raw_text:
                        option_key = "对" if "对" in option_raw_text else "错";
                        options[option_key] = option_key
            correct_answer_element = question_item.find('label', {'for': lambda x: x and x.endswith('_option_Answer')})
            correct_answer = ""
            if correct_answer_element:
                p_tag = correct_answer_element.find('p')
                if p_tag:
                    correct_answer = p_tag.get_text(strip=True)
                else:
                    answer_text = correct_answer_element.get_text(strip=True)
                    correct_answer = answer_text.replace("正确答案:", "").strip()
            if question_text and options and correct_answer:
                all_questions_data.append(
                    {'id': question_id, 'type': question_type, 'question': question_text, 'options': options,
                     'correct_answer': correct_answer})
    return all_questions_data


# --- Kivy界面定义 ---

# --- 关键修改：引入ThemedPopup ---
class ThemedPopup(Popup):
    pass


def show_popup(title, text):
    content = BoxLayout(orientation='vertical', padding='10dp', spacing='10dp')
    content.add_widget(Label(text=text, font_name='NotoSansSC-Regular.ttf'))
    close_button = Button(text='关闭', font_name='NotoSansSC-Regular.ttf', size_hint_y=None, height='48dp')
    content.add_widget(close_button)
    popup = ThemedPopup(title=title, content=content, size_hint=(0.85, 0.35))
    close_button.bind(on_press=popup.dismiss)
    popup.open()


class ListItemCard(BoxLayout):
    title = StringProperty('')
    subtitle = StringProperty('')


class ReviewItemCard(BoxLayout):
    question_text = StringProperty('')
    user_answer_text = StringProperty('')
    correct_answer_text = StringProperty('')
    item_color = ListProperty([1, 1, 1, 1])


class QuizOption(RelativeLayout):
    text = StringProperty('')
    group = StringProperty(None)
    active = BooleanProperty(False)
    disabled = BooleanProperty(False)
    option_key = StringProperty('')
    # feedback_state 可以是 'normal', 'correct', 或 'wrong'
    feedback_state = OptionProperty('normal', options=['normal', 'correct', 'wrong'])


# 在 main.py 中找到并完整替换 StartScreen 类
class StartScreen(Screen):
    def on_enter(self, *args):
        Clock.schedule_once(self.populate_lists)

    def populate_lists(self, dt=None):
        self.ids.in_progress_list.clear_widgets()
        self.ids.new_quiz_list.clear_widgets()
        data = load_data()
        if not data.get('in_progress'):
            # --- 关键修改：为这个动态Label添加字体和尺寸，确保显示完全 ---
            label = Label(text="没有未完成的练习。", color=(0.5, 0.5, 0.5, 1), font_name='NotoSansSC-Regular.ttf',
                          size_hint_y=None, height='40dp')
            self.ids.in_progress_list.add_widget(label)
        else:
            # 按时间倒序排列未完成的练习
            in_progress_items = sorted(data['in_progress'].items(), key=lambda item: float(item[0]), reverse=True)
            for session_id, session_data in in_progress_items:
                subject_display_name = os.path.splitext(session_data['subject'])[0]
                mode_text = "练习" if session_data.get('mode', 'all') == 'all' else "考试"

                # --- 关键修改：在副标题中加入格式化的保存时间 ---
                save_time = datetime.fromtimestamp(float(session_id)).strftime('%m-%d %H:%M')
                subtitle_text = f"{mode_text} - 保存于 {save_time}"

                card = ListItemCard(title=subject_display_name, subtitle=subtitle_text)
                card.ids.action_button.text = '继续'
                card.ids.action_button.bind(on_press=lambda x, s=session_data: self.start_quiz(s))
                self.ids.in_progress_list.add_widget(card)

        subjects = sorted(glob.glob('*.htm') + glob.glob('*.html'))
        if not subjects:
            label = Label(text="未在本文件夹中找到任何 .htm 或 .html 文件！", color=(1, 0, 0, 1),
                          font_name='NotoSansSC-Regular.ttf', size_hint_y=None, height='40dp')
            self.ids.new_quiz_list.add_widget(label)
        else:
            for subject_file in subjects:
                subject_display_name = os.path.splitext(subject_file)[0]
                card = ListItemCard(title=subject_display_name, subtitle='开始新的挑战')
                card.ids.action_button.text = '练习模式'
                card.ids.action_button.bind(
                    on_press=lambda x, s=subject_file: self.start_quiz({'subject': s, 'mode': 'all'}))
                exam_button = Button(text='模拟考试', font_name='NotoSansSC-Regular.ttf', size_hint_x=0.4)
                exam_button.bind(on_press=lambda x, s=subject_file: self.start_quiz({'subject': s, 'mode': 'exam'}))
                card.ids.button_box.add_widget(exam_button)
                self.ids.new_quiz_list.add_widget(card)

    def start_quiz(self, context):
        self.manager.get_screen('quiz').start(context)
        self.manager.current = 'quiz'

    def go_to_history(self):
        self.manager.current = 'history'

    def confirm_delete_records(self):
        content = BoxLayout(orientation='vertical', padding='10dp', spacing='10dp')
        content.add_widget(Label(text='您确定要删除所有记录吗？\n此操作不可恢复。', font_name='NotoSansSC-Regular.ttf'))
        button_layout = BoxLayout(size_hint_y=None, height='48dp', spacing='10dp')
        yes_button = Button(text='确定', font_name='NotoSansSC-Regular.ttf',
                            background_color=get_color_from_hex('#C62828'), color=(1, 1, 1, 1))
        no_button = Button(text='取消', font_name='NotoSansSC-Regular.ttf')
        button_layout.add_widget(yes_button)
        button_layout.add_widget(no_button)
        content.add_widget(button_layout)
        popup = ThemedPopup(title='确认操作', content=content, size_hint=(0.85, 0.4))

        def delete_and_dismiss(instance):
            if delete_all_records():
                show_popup("成功", "所有记录已成功删除！")
                Clock.schedule_once(self.populate_lists)
            else:
                show_popup("提示", "没有找到记录文件。")
            popup.dismiss()

        yes_button.bind(on_press=delete_and_dismiss)
        no_button.bind(on_press=popup.dismiss)
        popup.open()


class HistoryScreen(Screen):
    def on_enter(self, *args):
        Clock.schedule_once(self.populate_history)

    def populate_history(self, dt=None):
        self.ids.history_list.clear_widgets()
        self.records = sorted(load_data().get('completed', []), key=lambda x: x['timestamp'], reverse=True)
        if not self.records:
            self.ids.history_list.add_widget(Label(text='没有历史记录。', font_name='NotoSansSC-Regular.ttf'))
            return
        for record in self.records:
            subject_display_name = os.path.splitext(record['subject'])[0]
            time_str = datetime.fromtimestamp(record['timestamp']).strftime('%Y-%m-%d %H:%M')
            card = ListItemCard(title=f"{subject_display_name} ({record['score']}/{record['total']})",
                                subtitle=time_str)
            card.ids.action_button.text = '复习错题'
            card.ids.action_button.bind(on_press=lambda x, r=record: self.review_wrong(r))
            self.ids.history_list.add_widget(card)

    def review_wrong(self, session_data):
        if not session_data.get('wrong_question_ids'):
            show_popup("恭喜", "该次练习没有错题！")
            return
        context = {'subject': session_data['subject'], 'mode': 'review_history',
                   'question_ids': session_data['wrong_question_ids']}
        self.manager.get_screen('quiz').start(context)
        self.manager.current = 'quiz'


class ReviewScreen(Screen):
    def set_review_data(self, questions, user_answers):
        self.ids.review_list.clear_widgets()
        for i, q_data in enumerate(questions):
            user_ans = user_answers.get(q_data['id'], "未作答")
            is_correct = (user_ans == q_data['correct_answer'])
            card = ReviewItemCard(question_text=f"{i + 1}. {q_data['question']}",
                                  user_answer_text=f"你的答案: {user_ans}",
                                  correct_answer_text=f"正确答案: {q_data['correct_answer']}",
                                  item_color=get_color_from_hex('#e8f5e9') if is_correct else get_color_from_hex(
                                      '#ffebee'))
            self.ids.review_list.add_widget(card)


class QuizScreen(Screen):
    question_type_text = StringProperty('')
    question_info_text = StringProperty('')
    question_text = StringProperty('')
    feedback_text = StringProperty('')
    feedback_color = ListProperty([0, 0, 0, 1])
    score_text = StringProperty('')

    def go_back_to_start(self):
        if len(self.user_answers) == self.total_questions or self.mode == 'review_history':
            self.manager.current = 'start'
            return
        content = BoxLayout(orientation='vertical', padding='10dp', spacing='10dp')
        content.add_widget(Label(text='要保存当前进度，以便下次继续吗？', font_name='NotoSansSC-Regular.ttf'))
        button_layout = BoxLayout(size_hint_y=None, height='48dp', spacing='10dp')
        yes_button = Button(text='保存并退出', font_name='NotoSansSC-Regular.ttf',
                            background_color=get_color_from_hex('#1976D2'), color=(1, 1, 1, 1))
        no_button = Button(text='直接退出', font_name='NotoSansSC-Regular.ttf')
        button_layout.add_widget(yes_button)
        button_layout.add_widget(no_button)
        content.add_widget(button_layout)
        popup = ThemedPopup(title='保存进度？', content=content, size_hint=(0.9, 0.4))

        def save_and_exit(instance):
            data = load_data()
            data['in_progress'][str(self.session_id)] = {'session_id': self.session_id, 'subject': self.subject_file,
                                                         'mode': self.mode, 'question_ids': self.question_ids,
                                                         'current_index': self.current_question_index,
                                                         'user_answers': self.user_answers,
                                                         'wrong_in_this_session': self.wrong_in_this_session,
                                                         'total_questions': self.total_questions}
            save_data(data)
            show_popup("已保存", "进度已保存，可在主菜单继续。")
            popup.dismiss()
            self.manager.current = 'start'

        def exit_without_saving(instance):
            popup.dismiss()
            self.manager.current = 'start'

        yes_button.bind(on_press=save_and_exit)
        no_button.bind(on_press=exit_without_saving)
        popup.open()

    def start(self, context):
        self.context = context
        self.subject_file = context['subject']
        self.mode = context['mode']
        self.subject_display_name = os.path.splitext(self.subject_file)[0]
        all_questions = extract_questions_from_html(self.subject_file)
        if not all_questions:
            show_popup("错误", f"无法从 {self.subject_file} 加载任何题目。")
            self.manager.current = 'start'
            return
        self.all_questions_map = {q['id']: q for q in all_questions}
        self.user_answers = context.get('user_answers', {})
        if 'session_id' in context and self.mode != 'review_history':
            self.session_id = context['session_id']
            self.question_ids = context['question_ids']
            self.current_question_index = context['current_index']
            self.wrong_in_this_session = context.get('wrong_in_this_session', [])
        elif self.mode == 'exam':
            self.session_id = datetime.now().timestamp()
            EXAM_TOTAL = 55
            if len(all_questions) <= EXAM_TOTAL:
                self.question_ids = list(self.all_questions_map.keys())
            else:
                categorized_questions = {"单选题": [], "多选题": [], "判断题": []}
                for q in all_questions:
                    if q['type'] in categorized_questions:
                        categorized_questions[q['type']].append(q)
                total_source_questions = len(all_questions)
                num_to_sample = {}
                sampled_so_far = 0
                for q_type, q_list in categorized_questions.items():
                    if not q_list: continue
                    num = int(round((len(q_list) / total_source_questions) * EXAM_TOTAL))
                    num_to_sample[q_type] = num
                    sampled_so_far += num
                remainder = EXAM_TOTAL - sampled_so_far
                if remainder != 0:
                    largest_category = max(categorized_questions, key=lambda k: len(categorized_questions[k]))
                    num_to_sample[largest_category] += remainder
                final_exam_questions = []
                for q_type, num in num_to_sample.items():
                    q_pool = categorized_questions[q_type]
                    actual_num_to_sample = min(num, len(q_pool))
                    final_exam_questions.extend(random.sample(q_pool, actual_num_to_sample))
                self.question_ids = [q['id'] for q in final_exam_questions]
            random.shuffle(self.question_ids)
            self.current_question_index = 0
            self.wrong_in_this_session = []
        else:
            if self.mode == 'review_history':
                self.session_id = None
                self.question_ids = context['question_ids']
            else:
                self.session_id = datetime.now().timestamp()
                self.question_ids = list(self.all_questions_map.keys())
                random.shuffle(self.question_ids)
            self.current_question_index = 0
            self.wrong_in_this_session = []
        self.questions = [self.all_questions_map[qid] for qid in self.question_ids if qid in self.all_questions_map]
        self.total_questions = len(self.questions)
        self.max_reached_index = len(self.user_answers)
        self.display_question()

    def display_question(self):
        self.ids.options_box.clear_widgets()
        q_data = self.questions[self.current_question_index]
        mode_display_text = "模拟考试" if self.mode == 'exam' else "练习模式"
        if self.mode == 'review_history': mode_display_text = '错题复习'
        self.question_type_text = q_data['type']
        self.question_info_text = f" - {self.subject_display_name} ({mode_display_text})"
        self.question_text = f"{self.current_question_index + 1}/{self.total_questions}. {q_data['question']}"
        is_answered = q_data['id'] in self.user_answers
        user_selection = self.user_answers.get(q_data['id'])

        # 遍历选项并创建
        for key, value in q_data['options'].items():
            display_text = f"{key}. {value}" if key not in ["对", "错"] else value
            option = QuizOption(text=display_text, option_key=key)
            if q_data['type'] in ["单选题", "判断题"]:
                option.group = 'single_choice'

            # 如果题目已作答，设置选项的状态
            if is_answered:
                option.disabled = True
                correct_answer = q_data['correct_answer']
                # 如果是用户选中的选项
                if key in user_selection:
                    option.feedback_state = 'correct' if user_selection == correct_answer else 'wrong'
                # 如果不是用户选中的，但却是正确答案
                elif key in correct_answer and user_selection != correct_answer:
                    option.feedback_state = 'correct'
            self.ids.options_box.add_widget(option)

        self.ids.submit_button.disabled = is_answered
        if is_answered:
            correct_answer = q_data['correct_answer']
            is_correct = (user_selection == correct_answer)
            self.feedback_text = f"您选择的答案是: {user_selection}\n{'回答正确！' if is_correct else '回答错误。正确答案是: ' + correct_answer}"
            self.feedback_color = get_color_from_hex('#2E7D32') if is_correct else get_color_from_hex('#C62828')
        else:
            self.feedback_text = ""
        self.update_score_and_nav_buttons()

    def update_score_and_nav_buttons(self):
        answered_count = len(self.user_answers)
        correct_count = sum(
            1 for qid, ans in self.user_answers.items() if ans == self.all_questions_map[qid]['correct_answer'])
        self.score_text = f"进度: {answered_count}/{self.total_questions} | 正确: {correct_count}"
        self.ids.prev_button.disabled = self.current_question_index <= 0
        is_current_answered = self.questions[self.current_question_index]['id'] in self.user_answers
        self.ids.next_button.disabled = not (
                    is_current_answered and self.current_question_index < self.total_questions - 1)
        if answered_count == self.total_questions:
            self.ids.next_button.text = "查看结果"
            self.ids.next_button.disabled = False
        else:
            self.ids.next_button.text = "下一题"

    def check_answer(self):
        q_data = self.questions[self.current_question_index]
        user_selection = ""
        active_options = [child for child in self.ids.options_box.children if child.active]
        if not active_options:
            show_popup("提示", "请选择一个答案！")
            return
        if q_data['type'] in ["单选题", "判断题"]:
            user_selection = active_options[0].option_key
        elif q_data['type'] == "多选题":
            selected_keys = [child.option_key for child in reversed(active_options)]
            user_selection = "".join(sorted(selected_keys))
        self.user_answers[q_data['id']] = user_selection
        is_correct = (user_selection == q_data['correct_answer'])
        if not is_correct and self.mode != 'review_history':
            if q_data['id'] not in self.wrong_in_this_session:
                self.wrong_in_this_session.append(q_data['id'])
        self.max_reached_index = max(self.max_reached_index, self.current_question_index + 1)
        self.display_question()

    def prev_question(self):
        if self.current_question_index > 0:
            self.current_question_index -= 1
            self.display_question()

    def next_question(self):
        if self.ids.next_button.text == '查看结果':
            self.finish_quiz()
            return
        is_current_answered = self.questions[self.current_question_index]['id'] in self.user_answers
        if self.current_question_index < self.total_questions - 1 and is_current_answered:
            self.current_question_index += 1
            self.display_question()

    def finish_quiz(self):
        if self.mode != 'review_history' and self.session_id:
            data = load_data()
            if str(self.session_id) in data['in_progress']:
                del data['in_progress'][str(self.session_id)]
            final_score = sum(
                1 for qid, ans in self.user_answers.items() if ans == self.all_questions_map[qid]['correct_answer'])
            wrong_question_ids = [qid for qid, ans in self.user_answers.items() if
                                  ans != self.all_questions_map[qid]['correct_answer']]
            data['completed'].append(
                {'timestamp': self.session_id, 'subject': self.subject_file, 'mode': self.mode, 'score': final_score,
                 'total': self.total_questions, 'wrong_question_ids': wrong_question_ids})
            save_data(data)
        review_screen = self.manager.get_screen('review')
        review_screen.set_review_data(self.questions, self.user_answers)
        self.manager.current = 'review'


class QuizApp(App):
    def build(self):
        pass


if __name__ == '__main__':
    QuizApp().run()