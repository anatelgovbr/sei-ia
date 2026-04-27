# from api_sei.pydantic_models.log_recommendation import LogRecommendation
# from api_sei.pydantic_models.document_recommenders import DocumentRecommendation
# from api_sei.pydantic_models.process_recommenders import ProcessRecommendation
# from api_sei.repository.recommendation import add_log_recommendation, add_process_recommendation

# from fastapi import HTTPException

# def create_log_recommendation(log_recommendation: LogRecommendation):
#     try:
#         return add_log_recommendation(log_recommendation)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# def create_document_recommendation(document_recommendation: DocumentRecommendation):
#     try:
#         return add_document_recommendation(document_recommendation)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# def create_process_recommendation(process_recommendation: ProcessRecommendation):
#     try:
#         return add_process_recommendation(process_recommendation)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
