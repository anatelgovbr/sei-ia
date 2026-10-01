"""text_clean module."""

import re


def only_numbers(s):
    """Keeps only numbers."""
    if isinstance(s, int):
        return s
    return re.sub(r"[^\d\s]", "", str(s))


def remove_sep_token(text):
    """Removes <SEP> token."""
    text = text.replace("<SEP>", " ")
    return re.sub(r"[\s]+", " ", text)


def remove_encoding(text) -> str:
    """Remove erro de encoding."""
    text = text.replace("\xa0", " ")
    text = text.encode("utf-8", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[\n\t\r]", " ", text)
    return re.sub(r" +", " ", text)


def pandas_timestamp_to_solr_datepointfield(pandas_timestamp):
    return pandas_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def adapt_date(df, col_name):
    """https://solr.apache.org/guide/6_6/working-with-dates.html#WorkingwithDates-DateFormatting
    https://stackoverflow.com/questions/55021984/python-3-how-to-format-to-yyyy-mm-ddthhmmssz.
    """
    df[col_name] = df[col_name].apply(pandas_timestamp_to_solr_datepointfield)
    return df


def adapt_nr_processo(df, col_name="nr_processo"):
    """Processa dataframe com coluna nr_processo.

    Args:
        df : pandas dataframe com uma coluna nr_processo

    Returns:
        df : igual a entrada, mas com caracteres especiais removidos da coluna nr_processo
    """
    df[col_name] = df[col_name].apply(only_numbers)

    return df
