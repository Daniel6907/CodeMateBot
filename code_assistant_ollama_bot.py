import os
import re
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler
import httpx

# Завантажуємо змінні оточення з файлу .env
load_dotenv()

# Отримуємо токен Telegram бота
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Перевіряємо, чи отримали ми токен. Якщо ні - зупиняємо програму з помилкою.
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не знайдено в .env файлі або змінних оточення.")

# --- КОНФІГУРАЦІЯ OLLAMA ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL_NAME = "codellama"

print(f"Буде використана модель Ollama: {OLLAMA_MODEL_NAME} за адресою {OLLAMA_API_URL}")

# --- Функція для екранування MarkdownV2 ---
def escape_markdown_v2(text: str) -> str:
    """
    Екранує спеціальні символи MarkdownV2.
    Ця функція тепер очікує, що код вже витягнуто і відформатовано,
    і вона лише екранує будь-які залишки спецсимволів у чистому тексті.
    """
    # Символи, які потрібно екранувати в MarkdownV2
    escape_chars = r'_*[]()~`>#+=-|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# --- НОВА ФУНКЦІЯ: Витягування кодових блоків з відповіді Ollama ---
def extract_code_blocks(text: str) -> str:
    """
    Витягує всі блоки коду Markdown (```lang\ncode\n```) з тексту
    і повертає їх об'єднаними. Якщо код не знайдено, повертає оригінальний текст.
    """
    code_blocks = re.findall(r'```(?:python|py|go|java|javascript|js|c\+\+|cpp|c|html|css|php|ruby|rust|shell|bash|zsh|yaml|json|sql|markdown|txt|xml|diff)?\n(.*?)?\n```', text, re.DOTALL)
    
    if code_blocks:
        # Об'єднуємо всі знайдені кодові блоки
        # Додаємо назад ```python\n та ``` для коректного форматування в Telegram
        formatted_code = "\n\n".join([f"```python\n{block.strip()}\n```" for block in code_blocks])
        return formatted_code
    else:
        # Якщо кодових блоків не знайдено, повертаємо текст як є (або можна повернути повідомлення про помилку)
        print("Попередження: Кодові блоки не знайдено у відповіді Ollama. Повертаю весь текст.")
        # Для випадків, коли Ollama не генерує саме код, а звичайний текст,
        # ми його теж екрануємо на випадок спецсимволів
        return escape_markdown_v2(text)

# --- Функції обробки команд Telegram ---
async def start(update: Update, context) -> None:
    """Обробляє команду /start."""
    welcome_message = (
        'Привіт! Я твій помічник з Python коду на базі локальної моделі Ollama. '
        'Ти можеш попросити мене проаналізувати, виправити або написати код.\n\n'
        'Використовуй:\n'
        '<code>/analyze &lt;код&gt;</code> - для аналізу коду\n'
        '<code>/fix &lt;код&gt;</code> - для виправлення коду\n'
        '<code>/write &lt;опис_задачі&gt;</code> - для генерації коду'
    )
    await update.message.reply_text(welcome_message, parse_mode='HTML')

async def help_command(update: Update, context) -> None:
    """Обробляє команду /help."""
    help_text = (
        'Я можу допомогти тобі з Python кодом:\n'
        '<code>/analyze &lt;код&gt;</code> - проаналізувати наданий Python код.\n'
        '<code>/fix &lt;код&gt;</code> - спробувати виправити помилки в Python коді.\n'
        '<code>/write &lt;опис_задачі&gt;</code> - згенерувати Python код за описом.\n\n'
        'Приклад: <code>/analyze print("Hello World!")</code>\n'
        'Приклад: <code>/fix def foo(x): print(x / 0)</code>\n'
        'Приклад: <code>/write написати функцію, яка обчислює факторіал числа</code>'
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

# --- Функція взаємодії з Ollama API ---
async def send_to_ollama(system_instruction: str, user_prompt: str, temperature: float = 0.7) -> str:
    """Відправляє запит до локального сервера Ollama та повертає відповідь."""
    full_prompt = f"{system_instruction}\n\n{user_prompt}"

    payload = {
        "model": OLLAMA_MODEL_NAME,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 1500
        }
    }

    print(f"Відправляю запит до Ollama. Модель: {OLLAMA_MODEL_NAME}. Промпт (перші 200 символів):\n{full_prompt[:200]}...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OLLAMA_API_URL, json=payload, timeout=300.0)
            response.raise_for_status()

            response_data = response.json()
            generated_text = response_data.get("response", "")

            print(f"Отримано відповідь від Ollama (перші 500 символів):\n{generated_text[:500]}")
            
            # НОВА ЛОГІКА: Витягуємо лише кодові блоки з відповіді
            return extract_code_blocks(generated_text)

    except httpx.RequestError as e:
        error_message = (
            f"Помилка мережі або таймаут при зверненні до Ollama API: {e}. "
            f"Переконайтеся, що Ollama запущена і модель '{OLLAMA_MODEL_NAME}' завантажена."
        )
        print(error_message)
        # Помилка мережі або таймаут - повертаємо екрановане повідомлення про помилку
        return escape_markdown_v2(
            f"Виникла мережева помилка під час звернення до Ollama: {e}. "
            f"Будь ласка, перевірте, чи запущено Ollama та чи доступна модель `{OLLAMA_MODEL_NAME}`\\."
        )
    except httpx.HTTPStatusError as e:
        error_message = (
            f"Помилка HTTP статусу від Ollama API: {e.response.status_code} - {e.response.text}. "
            f"Можливо, модель '{OLLAMA_MODEL_NAME}' не завантажена або вказана невірно."
        )
        print(error_message)
        # Помилка HTTP статусу - повертаємо екрановане повідомлення про помилку
        return escape_markdown_v2(
            f"Отримано помилку від Ollama: `{e.response.status_code}`\\: `{e.response.text}`\\. "
            f"Можливо, модель не завантажена або вказана невірно\\."
        )
    except Exception as e:
        error_message = f"Невідома помилка при зверненні до Ollama API: {e}"
        print(error_message)
        # Загальна невідома помилка - повертаємо екрановане повідомлення про помилку
        return escape_markdown_v2(f"Виникла невідома помилка під час звернення до Ollama API: {e}\\. Будь ласка, спробуйте пізніше або зверніться до розробника\\.")

# --- Функції обробки коду ---
async def analyze_code(update: Update, context) -> None:
    """Аналізує наданий Python код за допомогою Ollama."""
    if not context.args:
        await update.message.reply_text(escape_markdown_v2("Будь ласка, надайте код для аналізу\\. Приклад: `/analyze print\\('Hello'\\)`"), parse_mode='MarkdownV2')
        return

    code_to_analyze = " ".join(context.args)

    # Важливо: ми просимо Ollama огорнути код у Markdown, тому системна інструкція це враховує
    system_instruction = "Ти експерт з Python програмування, який допомагає аналізувати код. Надай вичерпний аналіз, знайди можливі помилки, недоліки, запропонуй покращення та пояснення. Завжди огортай будь-який код у відповіді в блоки Markdown Python (```python\n...```)."
    user_prompt = f"Проаналізуй наступний Python код:\n\n```python\n{code_to_analyze}\n```"

    await update.message.reply_text("Аналізую код за допомогою Ollama, зачекайте...")

    analysis_result = await send_to_ollama(system_instruction, user_prompt, temperature=0.7)
    
    # Тепер escape_markdown_v2 буде обробляти лише текст, що не є кодом,
    # а extract_code_blocks вже подбає про форматування коду
    final_response = f"Результат аналізу:\n{analysis_result}"
    await update.message.reply_text(final_response, parse_mode='MarkdownV2')


async def fix_code(update: Update, context) -> None:
    """Виправляє наданий Python код за допомогою Ollama."""
    if not context.args:
        await update.message.reply_text(escape_markdown_v2("Будь ласка, надайте код для виправлення\\. Приклад: `/fix def foo\\(x\\): print\\(x / 0\\)`"), parse_mode='MarkdownV2')
        return

    code_to_fix = " ".join(context.args)

    system_instruction = "Ти експерт з Python, який спеціалізується на виправленні коду. Вияви та усунь помилки, якщо вони є, та поверни тільки виправлений код. Якщо код вже коректний, поверни його без змін. Завжди повертай код у блоках Markdown Python (```python\n...```) і без додаткових пояснень."
    user_prompt = f"Виправ наступний Python код:\n\n```python\n{code_to_fix}\n```"

    await update.message.reply_text("Виправляю код за допомогою Ollama, зачекайте...")

    fixed_code = await send_to_ollama(system_instruction, user_prompt, temperature=0.3)
    
    final_response = f"Виправлений код:\n{fixed_code}"
    await update.message.reply_text(final_response, parse_mode='MarkdownV2')

async def write_code(update: Update, context) -> None:
    """Пише Python код за описом задачі за допомогою Ollama."""
    if not context.args:
        await update.message.reply_text(escape_markdown_v2("Будь ласка, надайте опис задачі для написання коду\\. Приклад: `/write функцію, яка обчислює факторіал числа`"), parse_mode='MarkdownV2')
        return

    task_description = " ".join(context.args)

    system_instruction = "Ти експерт з Python, який пише чистий, ефективний та добре документований код. Завжди повертай тільки код у блоках Markdown Python (```python\n...```), без додаткових пояснень, окрім коментарів у самому коді."
    user_prompt = f"Напиши Python код, який виконує наступне завдання: {task_description}."

    await update.message.reply_text("Пишу код за допомогою Ollama, зачекайте...")

    generated_code = await send_to_ollama(system_instruction, user_prompt, temperature=0.8)
    
    final_response = f"Згенерований код:\n{generated_code}"
    await update.message.reply_text(final_response, parse_mode='MarkdownV2')

# --- Запуск бота ---
def main() -> None:
    """Запускає бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Додаємо обробники команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("analyze", analyze_code))
    application.add_handler(CommandHandler("fix", fix_code))
    application.add_handler(CommandHandler("write", write_code))

    print("Бот запущено. Очікування команд...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()