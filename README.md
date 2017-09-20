uml2sqlalchemy
==============

Parses UML XML file and generates SQLAlchemy ORM model.

- xmltodict.py was downloaded from  https://github.com/martinblech/xmltodict

Note that this is prototype code and can be significantly improved.
- It hasn't been tested using a wide variety of UML files. 
- It has no unit tests
- It has no robust error handling. 
- It may not know about some UML constructs. 
- It certainly has problems with relationships between tables, it sometimes generates n:m relationships where 1:n would suffice. 
- It generates 1:n relationships incorrectly where the foreign key is created, but not the backref wich could be very useful.

