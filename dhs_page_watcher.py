import requests
import os
import datetime
import json
import smtplib
import pandas as pd
from bs4 import BeautifulSoup as bs
from email.mime.text import MIMEText


def fetch_data():
    """Fetch data from DHS Available Datasets page."""
    url = "https://dhsprogram.com/data/available-datasets.cfm"
    response = requests.post(url=url)
    raw_content = str(response.content)
    return raw_content


def record_data(raw_content):
    """If data is new, record it to hard disk."""
    dir_path = os.path.dirname(os.path.realpath(__file__))
    new_dir = os.path.join(dir_path, datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
    os.makedirs(new_dir)
    with open(os.path.join(new_dir, "available_datasets.html"), "w") as html_file:
        html_file.write(raw_content)


def raw_content_to_table(raw_content):
    page = bs(raw_content, "lxml")
    rows = page.findAll("tr")
    firstTable = page.findAll("table")[0]
    headers = [th.text for th in firstTable.findAll("th")]
    row_data = [[cell.text.strip().replace("\\n", "") for cell in row.findAll("td")] for row in rows]
    pd_df = pd.DataFrame(row_data).drop_duplicates()
    pd_df.columns = headers
    return pd_df


def get_diff(old, new):
    old['SurveyType'] = old['Survey'].map(str) + old['Type']
    new['SurveyType'] = new['Survey'].map(str) + new['Type']
    cols_to_show = old.columns
    old['version'] = "old"
    new['version'] = "new"
    full_set = pd.concat([old, new], ignore_index=True)
    changes_old = full_set.drop_duplicates(subset=cols_to_show, keep='last')
    changes_old = changes_old[(changes_old['version'] == 'old')].drop(['version'], axis=1)
    changes_new = full_set.drop_duplicates(subset=cols_to_show, keep='first')
    changes_new = changes_new[(changes_new['version'] == 'new')].drop(['version'], axis=1)
    return changes_old, changes_new


def data_is_the_same(raw_content):
    """Check whether data has not changed."""
    dir_path = os.path.dirname(os.path.realpath(__file__))
    all_subdirs = [d for d in os.listdir(dir_path) if os.path.isdir(d) and d != ".git"]
    if len(all_subdirs) == 0:
        old_raw_content = fetch_data()
        record_data(old_raw_content)
        return True, old_raw_content
    latest_subdir = max(all_subdirs, key=os.path.getmtime)
    with open(os.path.join(dir_path, latest_subdir, "available_datasets.html"), "r") as html_file:
        old_raw_content = html_file.read()
    # 200 to bypass timestamp
    return (raw_content[200:] == old_raw_content[200:]), old_raw_content


def send_email(subject, message):
    """Send a notice"""
    conf = json.load(open("mail_conf.json"))
    fromEmail = conf["email1"]
    fromEmailPassword = conf["email1password"]
    recipients = conf["recipients"]

    message_wrapper = """\
    <html>
        <head></head>
        <body>
            {}
        </body>
    </html>
    """.format(message)

    msg = MIMEText(message_wrapper, 'html')
    msg['Subject'] = subject
    msg['From'] = fromEmail
    msg['To'] = ", ".join(recipients)

    smtp = smtplib.SMTP('smtp.gmail.com', 587)
    smtp.starttls()
    smtp.login(fromEmail, fromEmailPassword)
    smtp.sendmail(fromEmail, recipients, msg.as_string())
    smtp.quit()


def main():
    try:
        print("Fetching data...")
        raw_content = fetch_data()
    except Exception as e:
        print("Encountered an error fetching data...")
        send_email("DHS page fetch has failed", "<p>Error message: "+str(e)+"</p>")
    its_the_same, old_raw_content = data_is_the_same(raw_content)
    if its_the_same:
        print("Data is the same!")
    else:
        print("Data is not the same!")
        changes_old, changes_new = get_diff(raw_content_to_table(old_raw_content), raw_content_to_table(raw_content))
        record_data(raw_content)
        send_email(
            "DHS available data page has been updated",
            """\
            <p>The DHS Page Watcher has detected a change in the Available Datasets page.</p>
            <h2>Rows that appeared on older page</h2>
            {}
            </hr>
            <h2>Rows that now appear on newer page</h2>
            {}
            """.format(changes_old.to_html(), changes_new.to_html())
        )


if __name__ == '__main__':
    main()
