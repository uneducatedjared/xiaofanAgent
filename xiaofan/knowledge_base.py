from qdrant_client import QdrantClient, models
from langchain.text_splitter import RecursiveCharacterTextSplitter
from fastembed import TextEmbedding
from glob import glob
import os
from tqdm import tqdm


collection_name = "knowledge_base"
model_name = "BAAI/bge-small-en-v1.5"


client = QdrantClient(url="http://localhost:6333")
embedding_model = TextEmbedding(model_name=model_name, max_length=512)

def initialize_qdrant_knowledge_base(directory):
    markdown_files = glob(os.path.join(directory, "**/*.md"), recursive=True)
    print(markdown_files)
    
    # 1. 先创建集合（如果不存在）
    try:
        client.get_collection(collection_name=collection_name)
        print(f"集合 {collection_name} 已存在，将添加新数据。")
    except:
        # 集合不存在，创建它
        vector_size = 384
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        print(f"已创建新集合：{collection_name}")
    
    # 全局点 ID 计数器
    global_point_id = 0
    
    # 2. 处理所有文件
    all_points = []
    for file_path in tqdm(markdown_files, desc="Loading documents"):
        if not os.path.isfile(file_path):
            print(f"文件不存在：{file_path} 跳过")
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"错误：未找到知识库文件 '{file_path}'，跳过该文件。")
            continue
        except Exception as e:
            print(f"无法读取文件 '{file_path}': {e}，跳过该文件。")
            continue
        
        # 文本分块
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        docs = text_splitter.create_documents([content])
        print(f"文件 '{file_path}' 已分割成 {len(docs)} 个文本块。")
        
        # 为当前文件的文本块生成唯一 ID
        for i, doc in enumerate(docs):
            #doc.page_content 原始内容，文本对应的向量
            vector = list(embedding_model.embed(doc.page_content))[0]
            all_points.append(
                models.PointStruct(
                    id=global_point_id + i,  # 使用全局唯一 ID
                    vector=vector,
                    payload={
                        "text": doc.page_content,
                        "source": file_path  # 记录来源文件
                    }
                )
            )
        
        # 更新全局 ID 计数器
        global_point_id += len(docs)
    
    # 3. 批量上传所有点
    if all_points:
        client.upsert(
            collection_name=collection_name,
            wait=True,
            points=all_points
        )
        print(f"已成功将 {len(all_points)} 个文本块从 {len(markdown_files)} 个文件上传到 Qdrant 集合 '{collection_name}'。")
    else:
        print("没有有效的文本块可上传。")