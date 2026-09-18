from langchain_openai import ChatOpenAI

from app.infra.config.providers import infra_config
from app.shared.model import generate_embeddings, get_bge_m3_ef, get_llm_client, get_reranker_model

class LLMProvider:

    # 获取chat 文本模型  参数: 模型名字  JSON_Model
    def chat(self , model_name:str= None, json_mode:bool=False):
        return get_llm_client(model=model_name,json_mode=json_mode)

    # 获取vision_chat 视觉模型  允许传递 不传递给默认值
    def vision_chat(self,vision_model_name:str=None):
        """视觉模型客户端：优先独立 VL_API_* 配置（如硅基流动 VL 模型），
        未配置时回退统一 LLM 客户端（要求 LLM 供应商同时提供视觉模型）。"""
        vl_base = getattr(infra_config.llm, "vl_api_base", "")
        vl_key = getattr(infra_config.llm, "vl_api_key", "")
        model_name = vision_model_name or infra_config.llm.lv_model
        if vl_base and vl_key:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name, api_key=vl_key, base_url=vl_base, temperature=0.1)
        return get_llm_client(model=model_name)

    def embedding_mode(self):
        return get_bge_m3_ef()

    def embed_documents(self,documents:list[str]) -> dict[str,list]:
        """
            {
               dense: [[],[]], 1024
               sparse: [{index:xx},{}]
            }
        :param documents:
        :return:
        """
        return generate_embeddings(documents)

    def reranker_model(self):
        return get_reranker_model()

llm_provider  = LLMProvider()
