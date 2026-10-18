"""Streamlit UI calls backend over HTTP; it does not bypass the REST boundary."""
import os
from datetime import date
from uuid import uuid4
import requests
import streamlit as st
from config import ROOT
from platform_client import InventoryClient

st.set_page_config(page_title='Factory Maintenance Copilot', layout='wide')
st.title('Factory Maintenance Copilot')
st.caption('Synthetic factory demo • Evidence-first maintenance support')
base = os.getenv('COPILOT_URL', 'http://127.0.0.1:8000').rstrip('/')
intent = st.selectbox('Workflow (selected explicitly; no automatic intent inference)', ['combined', 'sop', 'analytics'])
question = st.text_area('Question', 'Which machine had the highest downtime? Show its main recorded fault, relevant SOP, and spare-part availability.')
left, right = st.columns(2)
start = left.date_input('Start date (UTC)', date(2026, 10, 1))
end = right.date_input('End date (inclusive, UTC)', date(2026, 10, 7))
machine = st.selectbox('Machine filter', ['All', 'M001', 'M002', 'M003'])
fault = st.text_input('Optional exact fault code (SOP workflow only)', '')
st.caption('Analytics supports downtime ranking and fault totals. Date and machine controls are authoritative; free-text questions do not generate SQL.')
if st.button('Investigate', type='primary'):
    if end < start:
        st.error('End date must be on or after start date.')
    else:
        try:
            with st.spinner('Collecting evidence…'):
                r = requests.post(f'{base}/ask', json={'question': question, 'intent': intent,
                    'start_date': str(start), 'end_date': str(end),
                    'machine_id': None if machine == 'All' else machine,
                    'fault_code': fault.strip().upper() or None}, timeout=(3, 180))
                r.raise_for_status()
                st.session_state.result = r.json()
                st.session_state.ticket_key = str(uuid4())
                st.session_state.pop('ticket_result', None)
        except requests.RequestException:
            st.error('Backend request failed. Check that api.py is running and inspect its terminal.')

if 'result' in st.session_state:
    result = st.session_state.result
    st.info(f"Generation: {result['answer']['mode']} | Retrieval: {result['retrieval_backend']} | {result['elapsed_seconds']} seconds")
    st.markdown(result['answer']['text'])
    evidence = result['evidence']
    if evidence.get('note'):
        st.warning(evidence['note'])
    for key in ['downtime', 'faults', 'inventory']:
        if evidence.get(key):
            st.subheader(key.replace('_', ' ').title())
            st.dataframe(evidence[key], width='stretch')
    st.subheader('SOP evidence')
    for source in evidence.get('sources', []):
        with st.expander(f"{source['source']} | similarity {source['score']}"):
            st.write(source['text'])
    with st.expander('Workflow trace and full evidence'):
        st.json(result)
    selected = evidence.get('selected_machine')
    if selected:
        st.subheader('Review a maintenance ticket')
        st.caption('Explicit submission to the local mock platform. No physical equipment is controlled.')
        with st.form('ticket'):
            description = st.text_area('Description', f"Review recorded downtime for {selected['machine_id']}. Investigate using approved procedures.")
            submitted = st.form_submit_button('Submit reviewed ticket')
        if submitted:
            try:
                ticket = {'machine_id': selected['machine_id'], 'fault_code': evidence.get('investigated_fault') or evidence['faults'][0]['fault_code'],
                          'description': description}
                st.session_state.ticket_result = InventoryClient().create_ticket(ticket, st.session_state.ticket_key)
            except requests.RequestException:
                st.error('Ticket submission failed or the same key was reused with changed content. Run a new investigation for a new ticket.')
        if st.session_state.get('ticket_result'):
            st.success('Ticket saved in the mock platform.')
            st.json(st.session_state.ticket_result)
