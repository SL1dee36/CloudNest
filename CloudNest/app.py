import os
import zipfile
import tarfile
from flask import Flask, render_template, request, send_from_directory, jsonify, url_for
from werkzeug.utils import secure_filename
import mimetypes
import shutil
from PIL import Image
from moviepy import VideoFileClip

app = Flask(__name__, static_folder='static')

# Конфигурация загрузок
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['THUMBNAIL_FOLDER'] = 'thumbnails/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024  # Максимальный размер файла 16GB

# Инициализация mimetypes
mimetypes.init()

# Создание папки для миниатюр, если ее нет
if not os.path.exists(app.config['THUMBNAIL_FOLDER']):
    os.makedirs(app.config['THUMBNAIL_FOLDER'])

def generate_thumbnail(filepath, filename):
    thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], f"{os.path.splitext(filename)[0]}.jpg")
    if os.path.exists(thumbnail_path):
        return thumbnail_path # Если миниатюра уже есть, возвращаем путь к ней
    try:
        mime_type = mimetypes.guess_type(filepath)[0]
        if mime_type and mime_type.startswith('image'):
            image = Image.open(filepath)
            
            # Получаем размеры изображения
            width, height = image.size

            # Определяем размер стороны квадрата для обрезки
            size = min(width, height)
            
            # Вычисляем координаты для обрезки, чтобы центр был неизменным
            left = (width - size) / 2
            top = (height - size) / 2
            right = (width + size) / 2
            bottom = (height + size) / 2

            # Обрезаем изображение
            image = image.crop((left, top, right, bottom))
            
            # Изменяем размер до желаемого размера миниатюры
            image = image.resize((200, 200))

            image.save(thumbnail_path)
        elif mime_type and mime_type.startswith('video'):
            clip = VideoFileClip(filepath)
            if clip.duration > 0:
                frame = clip.get_frame(min(1, clip.duration/2))
                img = Image.fromarray(frame)
                # Получаем размеры изображения
                width, height = img.size

                # Определяем размер стороны квадрата для обрезки
                size = min(width, height)
                
                # Вычисляем координаты для обрезки, чтобы центр был неизменным
                left = (width - size) / 2
                top = (height - size) / 2
                right = (width + size) / 2
                bottom = (height + size) / 2

                # Обрезаем изображение
                img = img.crop((left, top, right, bottom))
                
                # Изменяем размер до желаемого размера миниатюры
                img = img.resize((200, 200))
                img.save(thumbnail_path)
            clip.close()
        else:
            return None
        return thumbnail_path
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return None

# Главная страница
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        print("No file part")
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        print("No selected file")
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    print(f"Saving file: {filename} to {filepath}")

    try:
        # Сохраняем файл
        file.save(filepath)

        # Проверяем размер файла после сохранения
        file_size = os.path.getsize(filepath)
        print(f"File saved. Size: {file_size} bytes")

        update_file_list()
        return jsonify({'message': 'File uploaded successfully'})
    except Exception as e:
        print(f"Error saving file: {e}")
        return jsonify({'error': str(e)}), 500

# Скачивание файлов
@app.route('/uploads/<path:filename>')
def download_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404

# Удаление файла или папки
@app.route('/delete/<path:filename>', methods=['DELETE'])
def delete_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        if os.path.isdir(filepath):
            shutil.rmtree(filepath)  # Удаление директории со всем содержимым
        else:
            os.remove(filepath)
        
        # Удаление миниатюры
        thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], f"{os.path.splitext(filename)[0]}.jpg")
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            
        update_file_list()
        return jsonify({'message': 'File deleted successfully'})
    except OSError as e:
        return jsonify({'error': str(e)}), 500
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    
# Список файлов
@app.route('/list')
def list_files():
    items = []
    for item_name in os.listdir(app.config['UPLOAD_FOLDER']):
        item_path = os.path.join(app.config['UPLOAD_FOLDER'], item_name)
        is_dir = os.path.isdir(item_path)
        
        if is_dir:
            size = sum(os.path.getsize(os.path.join(item_path, f)) for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f)))
        else:
            size = os.path.getsize(item_path)
        
        # Определение, является ли файл архивом
        is_archive = False
        if not is_dir:
            mime_type = mimetypes.guess_type(item_path)[0]
            if mime_type and (mime_type.startswith('application/zip') or 
                             mime_type.startswith('application/x-rar-compressed') or
                             mime_type.startswith('application/x-7z-compressed') or
                             mime_type.startswith('application/x-tar') or
                             mime_type.startswith('application/gzip') or
                             mime_type.startswith('application/x-bzip2')):
                is_archive = True

        thumbnail_path = generate_thumbnail(item_path, item_name) # Генерируем или получаем миниатюру
        item_info = {
            'name': item_name,
            'is_dir': is_dir,
            'size': size,
            'type': mimetypes.guess_type(item_path)[0] or ('folder' if is_dir else 'Unknown'),
            'is_archive': is_archive,
           'thumbnail':  url_for('thumbnails', filename=os.path.basename(thumbnail_path)) if thumbnail_path else None
        }
        items.append(item_info)
    return jsonify({'items': items})

# Обновление списка файлов на клиенте
def update_file_list():
    # Эта функция просто вызывает list_files, которая возвращает обновленный список
    # Вы можете использовать эту функцию после загрузки или удаления файла
    return list_files()

@app.route('/edit/<path:filename>')
def edit_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.isfile(filepath):
        return jsonify({'error': 'File not found'}), 404
    if not is_editable_file(filename):
        return jsonify({'error': 'File is not editable'}), 403

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return render_template('edit.html', filename=filename, content=content)
    except UnicodeDecodeError:
        return jsonify({'error': 'File is not editable'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save/<path:filename>', methods=['POST'])
def save_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.isfile(filepath):
        return jsonify({'error': 'File not found'}), 404

    content = request.form['content']
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'message': 'File saved successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/extract/<path:filename>', methods=['POST'])
def extract_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.isfile(filepath):
        return jsonify({'error': 'File not found'}), 404

    extract_dir = os.path.splitext(filepath)[0]  # Папка для извлечения
    
    # Проверка, существует ли уже папка для извлечения
    if os.path.exists(extract_dir):
        return jsonify({'error': 'Extraction directory already exists'}), 400

    try:
        if zipfile.is_zipfile(filepath):
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        elif filepath.endswith('.tar.gz') or filepath.endswith('.tgz'):
            with tarfile.open(filepath, 'r:gz') as tar_ref:
                tar_ref.extractall(extract_dir)
        elif filepath.endswith('.tar.bz2') or filepath.endswith('.tbz'):
            with tarfile.open(filepath, 'r:bz2') as tar_ref:
                tar_ref.extractall(extract_dir)
        else:
            return jsonify({'error': 'Unsupported archive format'}), 400

        update_file_list()
        return jsonify({'message': 'Archive extracted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/folder/<path:foldername>')
def open_folder(foldername):
    folderpath = os.path.join(app.config['UPLOAD_FOLDER'], foldername)
    if not os.path.isdir(folderpath):
        return jsonify({'error': 'Folder not found'}), 404

    items = []
    for item_name in os.listdir(folderpath):
        item_path = os.path.join(folderpath, item_name)
        is_dir = os.path.isdir(item_path)

        if is_dir:
            size = sum(os.path.getsize(os.path.join(item_path, f)) for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f)))
        else:
            size = os.path.getsize(item_path)

        is_archive = False
        if not is_dir:
            mime_type = mimetypes.guess_type(item_path)[0]
            if mime_type and (mime_type.startswith('application/zip') or 
                             mime_type.startswith('application/x-rar-compressed') or
                             mime_type.startswith('application/x-7z-compressed') or
                             mime_type.startswith('application/x-tar') or
                             mime_type.startswith('application/gzip') or
                             mime_type.startswith('application/x-bzip2')):
                is_archive = True
                
        thumbnail_path = generate_thumbnail(item_path, item_name)
        
        item_info = {
            'name': item_name,
            'is_dir': is_dir,
            'size': size,
            'type': mimetypes.guess_type(item_path)[0] or ('folder' if is_dir else 'Unknown'),
            'is_archive': is_archive,
             'thumbnail':  url_for('thumbnails', filename=os.path.basename(thumbnail_path)) if thumbnail_path else None
        }
        items.append(item_info)

    return render_template('folder.html', foldername=foldername, items=items)

@app.route('/view/<path:filename>')
def view_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.isfile(filepath):
        return jsonify({'error': 'File not found'}), 404
    mime_type = mimetypes.guess_type(filepath)[0]
    if mime_type and mime_type.startswith(('image/', 'video/')):
         return render_template('view.html', filename=filename, mime_type=mime_type)
    else:
      return jsonify({'error': 'Can\'t view this file'}), 400

@app.route('/thumbnails/<path:filename>')
def thumbnails(filename):
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename)


def is_editable_file(filename):
    editable_extensions = ['.txt', '.html', '.css', '.js', '.py', '.json', '.xml', '.csv', '.md', '.log'] # и другие текстовые форматы
    return filename.lower().endswith(tuple(editable_extensions))

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)