import os
import json
import time
import logging
import boto3
from botocore.exceptions import ClientError
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract_client = boto3.client("textract")
sns_client = boto3.client("sns")

# Modelo para calcular el puntaje de similitud del texto extraido con la oferta
model = SentenceTransformer('distiluse-base-multilingual-cased-v1')

# aquí podríamos establecer palabras clave (skills, aptitudes...) que tengan los CV,
# y asignar puntuación a cada una de ellas
KEYWORDS = {
    "trabajo en equipo": 5,
    "aws": 10,
    "bases de datos": 5,
    "python": 8,
    "java": 5,
}


def lambda_handler(event, context):
    """
    Función principal que se invoca cuando se sube un cv al bucket
    """
    logger.info("trigger: %s", json.dumps(event, indent=2))

    for record in event["Records"]:
        bucket_name = record["s3"]["bucket"]["name"]
        object = record["s3"]["object"]["key"]

        logger.info(f"procesando CV: s3://{bucket_name}/{object}")

        # aquí iría el texto del CV a evaluar, después de que se complete textract
        extracted_text = extract_text_CV(bucket_name, object)

        topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
        if not topic_arn:
            logger.error("error envar: SNS_TOPIC_ARN")
            continue

        try:
            send_notification(evaluate_cv(extracted_text), bucket_name, object, topic_arn)
            logger.info(f"notificación enviada {topic_arn}")
        except ClientError as e:
            logger.error(f"ERROR: {e}")


def extract_text_CV(bucket, key):
   
    #TODO: Implementar servicio textract (debería devolver el texto en str)

    textract_client.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )

    return None


def evaluate_cv(text):
    """
    Evalúa el texto extraído del CV y asigna la puntuación con las keywords establecidas (case-insensitive)
    """
    total = 0
    for keyword, points in KEYWORDS.items():
        if keyword.lower() in text.lower():
            total += points
    return total

def calculate_similarity(text, job_vacancy):
    """
    Calcula la similitud del texto extraído del CV con el puesto ofertado
    """
    embedding_text = model.encode(text, convert_to_tensor=True)
    embedding_vacancy = model.encode(job_vacancy, convert_to_tensor=True)

    similarity_score = util.cos_sim(embedding_text, embedding_vacancy).item()

    return similarity_score

def send_notification(score, bucket, key, topic_arn):
    """
    Envía una notificación al tópico SNS con la puntuación y el nombre del archivo
    """

    msg = (
        f"Se ha recibido un nuevo CV: {bucket}\n"
        f"Archivo: {key}\n"
        f"Puntaje obtenido: {score}\n\n"
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    sns_client.publish(
        TopicArn=topic_arn, Message=msg, Subject="Nuevo CV Analizado - Resultado"
    )
