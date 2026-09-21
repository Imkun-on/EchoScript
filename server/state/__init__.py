"""Cio' che deve sopravvivere alla chiusura del programma.

Tre cose diverse, che hanno in comune il fatto di essere scritte su disco
perche' servono DOPO:

  ``credits``      quanto si e' consumato di Groq e quanto ne resta
  ``checkpoints``  a che pezzo di un video lungo si era arrivati
  ``jobs``         quali fasi di un lavoro sono gia' state fatte

Nessuno di questi moduli sa trascrivere o tradurre niente: sanno solo leggere
e scrivere foglietti, e rispondere a domande su quello che c'e' scritto.
"""
