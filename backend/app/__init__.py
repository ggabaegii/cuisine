from flask import Flask, render_template,request,jsonify,json, session
import requests
from .api import predict_from_image, get_recipes_from_gemini
from .database_operations import insert_recipes_to_db
import traceback
import os
from dotenv import load_dotenv
import sqlite3
import ast  # 문자열 데이터를 안전하게 리스트로 변환
import time


load_dotenv()

ROBOFLOW_API_URL = os.getenv("roboflow_API_URL")
ROBOFLOW_API_KEY = os.getenv("roboflow_API_KEY")

def parse_to_dict(value):
    try:
        # 문자열을 Python 객체로 변환
        parsed = ast.literal_eval(value)

        # 변환된 객체가 리스트인 경우, 각 항목이 문자열로 표현된 딕셔너리라면 변환
        if isinstance(parsed, list):
            return [ast.literal_eval(item) if isinstance(item, str) else item for item in parsed]
        
        # 변환된 객체가 딕셔너리인 경우 그대로 반환
        elif isinstance(parsed, dict):
            return parsed
        
        # 그 외의 경우는 원본 반환
        else:
            return parsed
    
    except (ValueError, SyntaxError):
        # 변환에 실패하면 원본 문자열 반환
        return value

def create_app():
    app = Flask(__name__, template_folder='templates')
    app.secret_key = 'your_secret_key'  # 세션 사용을 위한 비밀키 설정
    
    def fetch_all_recipes():
        conn = sqlite3.connect("C:/RecipeRecommendation/backend/app/database.db")  # DB 파일 이름
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM recipes")  # 레시피 이름과 이미지 경로 가져오기
        recipes = cursor.fetchall()  # [(name1, image_path1), (name2, image_path2), ...]
        conn.close()
        return recipes
   
    # 라우트 정의
    @app.route('/')
    def home():
        return render_template('mainpage.html')

    @app.route('/ingr_sea')
    def ingredients_search():
        # DB에서 레시피 데이터를 가져옴
        recipes = fetch_all_recipes()
        # 세션에서 선택된 재료 가져오기
        selected_ingredients = session.get('ingredients', [])
        # 선택된 재료를 콤마로 구분된 문자열로 변환
        selected_ingredients_str = ", ".join(selected_ingredients)
        # 이름만 추출하여 템플릿에 전달
        recipe_names = [recipe[1] for recipe in recipes]  # recipe[1]은 이름
        recipe_descriptions = [recipe[3] for recipe in recipes]
        recipe_ids = [recipe[0] for recipe in recipes]
        return render_template("ingrespage.html", recipe_names=recipe_names, recipe_descriptions=recipe_descriptions, recipe_ids=recipe_ids,selected_ingredients=selected_ingredients_str)
    
    @app.route('/send_ingredients_to_gemini', methods=['POST'])
    def send_ingredients_to_gemini():
        start_time = time.time()
        try:
            # 프론트엔드에서 받은 재료
            data = request.get_json()
            ingredients = data.get('ingredients', [])
            session['ingredients']=ingredients
    
            if not session['ingredients']:
                return jsonify({'error': '재료가 제공되지 않았습니다.'}), 400
        
            # 제미나이 API 호출
            recipes_data = get_recipes_from_gemini(session['ingredients'])
        
            # 레시피가 있는 경우 DB에 저장
            recipes = recipes_data.get('gemini_answer', {}).get('recipes', [])
            if recipes:
                insert_recipes_to_db(recipes)

            end_time = time.time()
            print(f"제미나이 API 호출 소요 시간: {end_time - start_time:.2f}초")
        
            # 성공적으로 응답 반환
            return jsonify({'recipes': recipes})

        except Exception as e:
            print("Error occurred:", traceback.format_exc())
            return jsonify({'error': str(e)}), 500    
    
    
    @app.route('/cooktip')
    def cooktip():
        return render_template('cooktip.html')
    

    @app.route('/cooktip_detail')
    def cooktip_detail():
        return render_template('cooktip_detail.html')
    

                    
    @app.route('/prdict', methods=['POST'])
    def predict():
        if 'file' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        file = request.files['file']

        try:
            # API 호출 함수
            yolo_result = predict_from_image(
                file,
                ROBOFLOW_API_URL,
                ROBOFLOW_API_KEY
            )
            ingredients = yolo_result.get('ingredients', [])
            
            # 선택된 재료를 세션에 저장
            session['ingredients'] = ingredients

            recipes_data = get_recipes_from_gemini(ingredients)

            recipes = recipes_data.get('gemini_answer', {}).get('recipes', [])

            if recipes:
                insert_recipes_to_db(recipes)


            return jsonify({'recipes': recipes})
        
        except Exception as e:
            print("Error occurred:", traceback.format_exc())
            return jsonify({'error': str(e)}), 500
        

    @app.route('/locspepage')
    def locspepage():
        return render_template('locspepage.html')
    


    @app.route('/mypagemain')
    def mypagemain():
        return render_template('mypagemain.html')
    
    @app.route('/mypagesub')
    def mypagesub():
        return render_template('mypagesub.html')
    
    # 상세 페이지 라우트
    @app.route("/recipe_detail/<int:recipe_id>")
    def recipe_detail(recipe_id):
        conn = sqlite3.connect("C:/RecipeRecommendation/backend/app/database.db")  # DB 파일 이름
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM recipes WHERE recipe_id = ?", (recipe_id,))
        recipe = cursor.fetchone()
        conn.close()
        ingredients = ast.literal_eval(recipe[4])  # 문자열 -> 리스트로 변환
        substitutes = ast.literal_eval(recipe[5])  # 문자열 -> 딕셔너리 변환
        instructions = ast.literal_eval(recipe[6])  # 문자열 -> 리스트로 변환
        # 재료 이름만 추출 (재료 이름은 첫 번째 공백 앞까지로 가정)
        ingredient_names = [ingredient.split()[0] for ingredient in ingredients]

        print(ingredients)
        print(substitutes)
        print(instructions)

        if recipe:
            return render_template("recipe_detail.html", name=recipe[1], category = recipe[2], description=recipe[3], ingredients=ingredients, ingredient_names=ingredient_names, substitutes=substitutes, instructions=instructions, cook_time = recipe[7], difficulty=recipe[8])
        else:
            return "Recipe not found", 404
        

    
    # @app.route('/recipe_detail')
    # def recipe_detail():
    #     return render_template('recipe_detail.html')

    @app.route('/recipe_main')
    def recipe_main():
        return render_template('recipe_main.html')
    

    @app.route('/recipe_register')
    def recipe_register():
        return render_template('recipe_register.html')


    @app.route('/recipe_search')
    def recipe_search():
        return render_template('recipe_search.html')

    @app.route('/searecpage')
    def searecpage():
        return render_template('searecpage.html')

    
    @app.route('/login')
    def login():
        return render_template('login.html')
    
    @app.route('/signup')
    def signup():
        return render_template('signup.html')

    # 사용자 정보 수정
    @app.route('/userinfo_edit', methods=['GET', 'POST'])
    def userinfo_edit():
        return render_template('userinfo_edit.html')

    return app
