import os
import pandas as pd
import sqlalchemy as db
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
####
from __init__ import DB_PATH

#-------------------------------------------------------------------------------------------------
#-----------DATABASE DEFINITION------------------------------------------------------
#-------------------------------------------------------------------------------------------------
Base = declarative_base()

class Isplate(Base): 
    __tablename__ = 'isplate'
    row_number = db.Column(db.Integer, primary_key=True)
    naziv_isplatitelja = db.Column(db.String)
    datum = db.Column(db.Date)
    primatelj = db.Column(db.String)
    oib = db.Column(db.String)
    mjesto = db.Column(db.String)
    proracunski_korisnik = db.Column(db.String)
    valuta = db.Column(db.String)
    iznos_na_poziciji = db.Column(db.Float)
    pozicija = db.Column(db.String)
    organizacijska_klasifikacija = db.Column(db.String)
    programska_klasifikacija = db.Column(db.String)
    izvor_financiranja = db.Column(db.String)
    ekonomska_klasifikacija = db.Column(db.String)
    funkcijska_klasifikacija = db.Column(db.String)
    broj_racuna = db.Column(db.String)
    opis = db.Column(db.String)
    datum_racuna = db.Column(db.Date)
    datum_dospijeca = db.Column(db.Date)
    iban = db.Column(db.String)
    poziv_na_broj = db.Column(db.String)

class DBHandler():
    def __init__(self):   
        self.db_engine = db.create_engine(f"sqlite:///{DB_PATH}")
        Base.metadata.create_all(self.db_engine)
        Session = sessionmaker()
        Session.configure(bind=self.db_engine)
        self.session = Session()

#-------------------------------------------------------------------------------------------------
#------------TBL MANIPULATION--------------------------------------------------------------
#-------------------------------------------------------------------------------------------------
    def store_csv_data(self, csv_file_path):
        data = pd.read_csv(csv_file_path, sep=';', encoding='utf-8')
        for _, row in data.iterrows():
            new_record = Isplate(
                naziv_isplatitelja=row['Naziv isplatitelja'],
                datum=pd.to_datetime(row['Datum']).date(),
                primatelj=row['Primatelj'],
                oib=row['OIB'],
                mjesto=row['Mjesto'],
                proracunski_korisnik=row['Proračunski korisnik'],
                valuta=row['Valuta'],
                iznos_na_poziciji=row['Iznos na poziciji'],
                pozicija=row['Pozicija'],
                organizacijska_klasifikacija=row['Organizacijska klasifikacija'],
                programska_klasifikacija=row['Programska klasifikacija'],
                izvor_financiranja=row['Izvor financiranja'],
                ekonomska_klasifikacija=row['Ekonomska klasifikacija'],
                funkcijska_klasifikacija=row['Funkcijska klasifikacija'],
                broj_racuna=row['Broj računa'],
                opis=row['Opis'],
                datum_racuna=pd.to_datetime(row['Datum računa']).date(),
                datum_dospijeca=pd.to_datetime(row['Datum dospijeća']).date(),
                iban=row['IBAN'],
                poziv_na_broj=row['Poziv na broj']
                )
            self.session.add(new_record)
        self.session.commit()
        #print(f'Data from {csv_file_path} stored in the database!')

    def empty_tbl(self):
        self.session.query(Isplate).delete()
        self.session.commit()
        print('Table emptied!')
    
    def get_last_date(self):
        last_date = self.session.query(db.func.max(Isplate.datum)).scalar()
        return last_date
    
    def check_duplicates(self):
        """ Ovo ne radi jer ima ogroman broj duplikata što su sve zasebne uplate bez distinkcije među sobom"""
        duplicates = self.session.query(
            Isplate.row_number,
            Isplate.primatelj,
            Isplate.iznos_na_poziciji,
            Isplate.datum,
            Isplate.broj_racuna,
            db.func.count('*').label('count')
        ).group_by(
            Isplate.primatelj,
            Isplate.iznos_na_poziciji,
            Isplate.datum,
            Isplate.broj_racuna
        ).having(
            db.func.count('*') > 1
        ).all()
        return duplicates
    
    def read_tbl(self):
        return self.session.query(Isplate).first()
    
#----------------------------------------------------------------------------------------------
#----------------TESTING-----------------------------------------------------------------------
#----------------------------------------------------------------------------------------------

if __name__ == '__main__':

    pydb = DBHandler()

    if False:
        pydb.empty_tbl()
    if False:
        from __init__ import DOWNLOAD_DIR
        filepath = os.path.join(DOWNLOAD_DIR, 'isplate_2024_01_05.csv')
        pydb.store_csv_data(filepath)
    if True:
        print(pydb.get_last_date())
    if False:
        print(pydb.check_duplicates())
    if False:
        from datetime import date
        pydb.session.query(Isplate).filter(Isplate.datum >= date(2025, 1, 1)).delete(synchronize_session=False)
        pydb.session.commit()
        print('Records with datum from 2025-01-01 deleted!')
        print(pydb.get_last_date())