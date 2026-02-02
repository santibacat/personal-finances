from thefuzz import process, fuzz
from modules import database
import pandas as pd

def get_tagging_knowledge_base():
    """Returns a dictionary of concept -> set of tags based on already tagged transactions."""
    df = database.get_all_transactions()
    if df.empty:
        return {}
    
    # Filtrar solo los que tienen tags
    df_tagged = df[df['tags_list'].notna() & (df['tags_list'] != '')]
    
    # Agrupar por concepto para tener una base de conocimientos
    # Concepto -> lista de tags (usamos el más frecuente o el último)
    kb = df_tagged.groupby('concept')['tags_list'].last().to_dict()
    return kb

def auto_tag_transactions(threshold=85):
    """
    Finds untagged transactions and tries to apply tags from similar historical concepts.
    Returns (applied_count, skipped_count).
    """
    kb = get_tagging_knowledge_base()
    if not kb:
        return 0, 0
    
    all_tx = database.get_all_transactions()
    untagged = all_tx[all_tx['tags_list'].isna() | (all_tx['tags_list'] == '')]
    
    if untagged.empty:
        return 0, 0
    
    applied_count = 0
    concepts_kb = list(kb.keys())
    
    for idx, row in untagged.iterrows():
        # Encontrar el concepto más parecido en la KB
        best_match, score = process.extractOne(row['concept'], concepts_kb, scorer=fuzz.token_set_ratio)
        
        if score >= threshold:
            tags_to_apply = kb[best_match].split(',')
            database.sync_transaction_tags(row['id'], [t.strip() for t in tags_to_apply])
            applied_count += 1
            
    return applied_count, len(untagged) - applied_count
