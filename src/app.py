﻿import os
import json
import time
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract_client = boto3.client("textract")
sns_client = boto3.client("sns")

# aquí podríamos establecer palabras clave (skills, aptitudes...) que tengan los CV,
# y asignar puntuación a cada una de ellas
KEYWORDS = {
    "trabajo en equipo": 10,
    "aws": 10,
    "bases de datos": 5,
    "python": 8,
    "java": 5,
    "docker": 6,
    "kubernetes": 8
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
        cv_data, extracted_text = extract_text_CV(bucket_name, object)
        topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
        if not topic_arn:
            logger.error("error envar: SNS_TOPIC_ARN")
            continue

        try:
            send_notification(cv_data, evaluate_cv(extracted_text), bucket_name, object, topic_arn)
            logger.info(f"notificación enviada {topic_arn}")
        except ClientError as e:
            logger.error(f"ERROR: {e}")


def extract_text_CV(bucket, key):
    """
    Extrae texto del CV utilizando Amazon Textract.
    """
    try:
        # Iniciar la detección de texto
        response = textract_client.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
        )

        job_id = response["JobId"]
        logger.info(f"Job iniciado con ID: {job_id}")

        # Esperar hasta que el trabajo esté completo
        while True:
            job_status = textract_client.get_document_text_detection(JobId=job_id)
            status = job_status["JobStatus"]

            if status in ["SUCCEEDED", "FAILED"]:
                break

            logger.info("Esperando a que Textract complete el trabajo...")
            time.sleep(5)

        cv_data = {}
        extracted_text = " "
        if status == "SUCCEEDED":
            logger.info("Textract completado exitosamente.")
            for block in job_status.get("Blocks", []):
                if block["BlockType"] == "LINE":
                    category = block ["Text"].split(':')
                    if len(category) > 1: 
                        cv_data[category[0].strip().lower()] = category[1]
                    else:
                        extracted_text += block["Text"] + " "
            return (cv_data, extracted_text)

        logger.error("Textract falló al procesar el documento.")
        return None

    except Exception as e:
        logger.error(f"Error al procesar Textract: {e}")
        return None


def evaluate_cv(text):
    """
    Evalúa el texto extraído del CV y asigna la puntuación con las keywords establecidas (case-insensitive)
    """
    total = 0
    for keyword, points in KEYWORDS.items():
        if keyword.lower() in text.lower():
            total += points
    logger.info(f"Puntuacion obtenida {total}")
    return total

def sumar_valores(diccionario):
    total = 0
    for valor in diccionario.values():
        total += valor
    return total

def send_notification(candidate_data, score, bucket, key, topic_arn):
    """
    Envía una notificación al tópico SNS con la puntuación y el nombre del archivo
    """
    total = sumar_valores(KEYWORDS)
    score = score / total * 10
    msg = (
        f"Se ha recibido un nuevo CV: {bucket}\n"
        f"Archivo: {key}\n"
        f"Nombre del candidato: {candidate_data["nombre"]}\n"
        f"Telefono: {candidate_data["tlf"]}\n"
        f"Direccion: {candidate_data["direccion"]}\n"
        f"Edad: {candidate_data["edad"]}\n"
        f"Email: {candidate_data["email"]}\n"
        f"GitHub: {candidate_data["github"]}\n"
        f"Linkedin: {candidate_data["linkedin"]}\n"
        f"Puntaje obtenido: {score}\n\n"
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    sns_client.publish(
        TopicArn=topic_arn, Message=msg, Subject="Nuevo CV Analizado - Resultado"
    )