
import xmltodict
import json
from urlparse import urlparse
import re
import textwrap
import argparse


basic_types = ['Integer', 'DateTime', 'Float', 'String', 'Boolean']

class_ids = dict()
type_ids = dict()
my_classes = []
my_types = []

last_added_list_type_id = 0

def find_id_for_type_name(new_type_name):
    result = None
    for id, class_name in class_ids.iteritems():
        if class_name== new_type_name:
            result = id
            break

    if not result:
        for id, type_name in type_ids.iteritems():
            if type_name == new_type_name:
                result = id
                break

    return result


def find_class_or_type(type_id) :
    result = None

    for class_ in my_classes:
        if class_.class_id == type_id:
            result = class_

    if not result:
        for type_ in my_types:
            if type_.type_id == type_id:
                result = type_

    return result

def convert_camel_case(name):
    """Convert camel case identifiers to python style with underscores"""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class MyConstraint:
    """Class that contains a constraint for an attribute"""

    def __init__(self, name, constraint_type, value=None):
        self.name = name
        self.type_id = constraint_type
        self.type_name = None
        self.value = value

    def __repr__(self):
        if self.type_name:
            result = "    # " + self.name + "(" + self.type_name + ")"
        else:
            result = "    # " + self.name + "(" + self.type_id + ")"

        if self.value:
            result += " = " + self.value

        return result.encode('ascii', 'ignore')

    def decorate_value(self, value):
        """returns a string containign the decorated value based upon the type of the constraint
        So String(1234) becomes '1234' and Integer(1234) becomes 1234
        """
        if self.type_name == 'uml:LiteralString':
            value = "'" + value + "'"
        else:
            # if all else fails, assume string
            value = "'" + value + "'"

        return value


    def get_default(self):
        default = None

        if self.name == 'defaultValue':
            if self.value:
                default = self.decorate_value(self.value)

        return default

    def resolve_type_ids(self):
        # Only resolve those that *don't* start with an _
        if self.type_id.startswith('_'):
            if self.type_id in class_ids:
                self.type_name = class_ids[self.type_id]
            else:
                if self.type_id in type_ids:
                    self.type_name = type_ids[self.type_id]

                self.type_ = self.find_type(self.type_id)

            # if self.type_name:
            #     print "Resolved %s into %s" % (self.type_id, self.type_name)
            # else:
            #     print "Failed to resolve type %s" % self.type_id

    def is_many_constraint(self):
        return self.value == '*'


class MyAttribute:
    """Class for a property inside a class, including type etc"""

    def __init__(self):
        # pass
        self.constraints = []
        self.name = None
        self.id = None
        self.type_id = None
        self.type_name = None
        self.comment = None

    def find_type(self, type_id):
        """Find the class object that has class_id as its unique ID"""
        for type_ in my_types:
            if type_.type_id == type_id:
                return type_

        return None

    def resolve_type_ids(self):
        if self.type_id in class_ids:
            self.type_name = class_ids[self.type_id]
            #print "~Found %s for %s for attribute %s" % (self.type_name, self.type_id, self.name)
            self.base_type_name = self.type_name
        else:
            if self.type_id in type_ids:
                self.type_name = type_ids[self.type_id]

            #print "Found %s for %s for attribute %s" % (self.type_name, self.type_id, self.name)

            self.type_ = self.find_type(self.type_id)

            # If the type of this attribute is an ENUM, set the type to the
            # SQLAlchemy type 'Enum'
            # Do the same for the other base types
            if self.type_:
                if isinstance(self.type_, MyEnumerationType) :
                    self.base_type_name = 'Enum'
                else :
                    if self.type_name == 'Real' :
                        self.base_type_name = 'Float'
                    else :
                        self.base_type_name = self.type_name
            else :
                if self.type_name == 'Real':
                    self.base_type_name = 'Float'
                else:
                    self.base_type_name = self.type_name

        if not self.base_type_name :
            self.base_type_name = "No base type?"

        #print "Base type is now %s" % (self.type_name)

        for constraint_ in self.constraints:
            constraint_.resolve_type_ids()

    def set_name(self, name):
        self.name = convert_camel_case(name)

    def set_id(self, id_):
        self.id = id_

    def set_type_id(self, type_id):
        # print "Changing type id for %s from %s to %s" % (self.name, self.type_id, type_id)
        self.type_id = type_id

    def set_type_name(self, type_name):
        self.type_name = type_name


    def set_comment(self, comment):
        comment = comment.replace('\n', ' ')
        comment = comment.replace('\r', ' ')
        comment = comment.replace('\"', '\'')

        self.comment = comment

    def add_constraint(self, constraint):
        self.constraints.append(constraint)

    def get_type(self):
        return self.type_

    def get_default(self):
        default = None

        for constraint_ in self.constraints:
            default = constraint_.get_default()

            if default:
                break

        return default

    def __repr__(self):
        result = ""

        result += "    \n    # "

        if self.name:
            result += self.name + "\n"

        if self.comment:
            width = 79
            comment = textwrap.fill(self.comment, width=width,
                                    initial_indent='    # ',
                                    subsequent_indent='    # ')
            result += comment
            result += "\n    # "

        for constraint_ in self.constraints:
            result += "\n" + repr(constraint_)

        result += "\n"

        default_value = self.get_default()

        if self.base_type_name == 'Enum' :
            result += "    " + self.name.lower() + " = "
            result += "Column('" + self.name.lower() + "', "
            result += self.base_type_name + "(*" + self.type_name + ")"

            # Requires SQLAlchemy 1.2 which hasn't been released yet
            # if self.comment:
            #     result += ", comment=\"" + self.comment.strip() + "\""

            # If default value, than use that and set nullable to False
            # Other wise set nullable to True (yes, that is lazy
            # Yes, the constraints shoudld tell us more
            if default_value:
                result += ", default = " + default_value
                result += ", nullable = False"
            else:
                result += ", nullable = True"
            result += ")"
        elif self.base_type_name in basic_types:
            result += "    " + self.name.lower() + " = "
            result += "Column('" + self.name.lower()+ "', "

            if self.base_type_name == 'String':
                result += self.base_type_name + "(100)"
            else:
                result += self.base_type_name

            # Requires SQLAlchemy 1.2 which hasn't been released yet
            # if self.comment:
            #     result += ", comment=\"" + self.comment.strip() + "\""

            if default_value:
                result += ", default = " + default_value
                result += ", nullable = False"
            else:
                result += ", nullable = True"
            result += ")"
            #if self.name:
            #    result += "        " + self.name.lower()
            #
            #if self.type_name:
            #    result += " = " + self.type_name + "()"
            #else:
            #    if self.type_id:
            #        result += " = " + self.type_id + "()"
        else:
            result += "    " + self.name.lower() + "_id = "
            result += "Column('" + self.name.lower() + "_id', "
            result += "ForeignKey('" + self.base_type_name.lower() + ".id'), nullable = True)"

        return result.encode('ascii', 'ignore') + "\n"

    def has_many_constraint(self):
        result = False
        for constraint in self.constraints:
            if constraint.is_many_constraint():
                result = True
                break
        return result



class MyClass:
    """Converts a class from a parsed UML file (XML) into a structure that can be used in various different ways"""

    def __init__(self, elements = None):
        self.attributes = []
        self.class_id = ""
        self.class_name = "MyClass"
        self.general_class_id = None
        self.general_class_name = None
        self.is_abstract = False
        self.general_class = None
        self.output = True

        if elements:
            self._parse_class_objects(elements)

    def find_general_class(self, class_id):
        """Find the class object that has class_id as its unique ID"""
        for class_ in my_classes:
            if class_.class_id == class_id:
                return class_

        return None

    def resolve_type_ids(self):
        """Resolve the types for the general class of this class. ALso resolve the types for each attribute"""
        if self.general_class_id:
            if self.general_class_id in class_ids:
                self.general_class_name = class_ids[self.general_class_id]
            else:
                if self.general_class_id in type_ids:
                    self.general_class_name = type_ids[self.general_class_id]

            self.general_class = self.find_general_class(self.general_class_id)

        for attribute_ in self.attributes:
            attribute_.resolve_type_ids()

        if len(self.attributes) == 1 :
            attribute_ = self.attributes[0]
            attribute_.resolve_type_ids()
            self.general_class_name = attribute_.base_type_name + " # one attribute, no need for seperate type, just use base type of the attribute"

    def __repr__(self):
        """Output a string representation of the class. If the class is an abstract class
        only output the attributes when called"""

        if not self.output :
            return ""

        # if self.is_abstract:
        #     result = "\n    # Properties inherited from " + self.class_name + "\n"
        #     if len(self.attributes) > 0:
        #         for attribute_ in self.attributes:
        #             result += repr(attribute_)
        #     # else:
        #     #     result += "\n    pass"
        #     result += "\n"
        #     result += "    # End of properties inherited from " + self.class_name + "\n"
        #     return result.encode('ascii', 'ignore')

        # Not an abstract class, so output as a full class
        result = "class "
        result += self.class_name

        result += "(Base): # class definition\n"

        result += "    __tablename__ = \'" + self.class_name.lower() + "\'\n\n"
        result += "    id = Column(Integer, primary_key=True)\n"


        # If this class has a general class, then add a foreign key to it
        if self.general_class:
            #result += repr(self.general_class)
            result += "    " + self.general_class_name.lower() + "_id = "
            result += "Column('" + self.general_class_name.lower() + "_id', "
            result += "ForeignKey('" + self.general_class_name.lower() + ".id'), nullable = True)"

        if len(self.attributes) > 0:
            for attribute_ in self.attributes:
                result += repr(attribute_)
        # else:
        #     result += "\n        pass"

        result += "\n"

        return result.encode('ascii', 'ignore')

    def set_name(self, name):
        """Set the name of this class.
        """
        self.class_name = name


    def _parse_class_objects(self, my_class_):
        # print(json.dumps(my_class_, indent=4))
        self.class_id = my_class_['@xmi:id']
        self.set_name(my_class_['@name'])

        if '@isAbstract' in my_class_:
            if my_class_['@isAbstract'] == 'true':
                self.is_abstract = True

        if 'ownedComment' in my_class_:
            self.comment = my_class_['ownedComment']['body']

        if 'generalization' in my_class_:
            self.general_class_id = my_class_['generalization']['@general']

        if 'ownedAttribute' in my_class_:
            self.attributes = self._parse_attributes(my_class_['ownedAttribute'])

        # Add our name to the main dictionary of class ids
        class_ids[self.class_id] = self.class_name

    @staticmethod
    def _parse_attributes(attributes):
        attribute_name = ""
        attribute_id = ""
        # attribute_type_id = ""
        new_attribute = None

        my_attributes = []

        for attribute_ in attributes:
            if isinstance(attribute_, basestring):
                # Attribute is a string, so there will probably be more strings to follow who will make up the
                # attribute. Once the last element of an attribute has been found, a new attribute will start.
                if attribute_ == '@name':
                    if new_attribute:
                        # We must have stepped into a new attribute. save the old one.
                        my_attributes.append(new_attribute)
                        new_attribute = None
                    attribute_name = attributes[attribute_]

                if attribute_ == '@xmi:id':
                    attribute_id = attributes[attribute_]

                if attribute_ == '@type':
                    # Trusting the once we reach @type, name and attribute ID have been seen
                    attribute_type = attributes[attribute_]
                    new_attribute = MyAttribute()
                    new_attribute.set_name(attribute_name)
                    new_attribute.set_id(attribute_id)
                    new_attribute.set_type_id(attribute_type)

                if attribute_ == 'ownedComment':
                    if new_attribute:
                        new_attribute.set_comment(attributes['ownedComment']['body'])

                if '@xmi:type' in attributes[attribute_]:
                    if '@value' in attributes[attribute_]:
                        my_constraint = MyConstraint(attribute_, attributes[attribute_]['@xmi:type'],
                                                     attributes[attribute_]['@value'])
                    else:
                        my_constraint = MyConstraint(attribute_, attributes[attribute_]['@xmi:type'])
                    new_attribute.add_constraint(my_constraint)
                else:
                    pass
            else:
                # The current attribute contains all the information about an attribute
                if attribute_['@xmi:type'] == 'uml:Property':
                    new_attribute = MyAttribute()

                    new_attribute.set_name(attribute_['@name'])
                    new_attribute.set_id(attribute_['@xmi:id'])
                    if '@type' in attribute_:
                        new_attribute.set_type_id(attribute_['@type'])

                    for parameter in attribute_:
                        if not parameter.startswith('@'):
                            if parameter == 'ownedComment':
                                new_attribute.set_comment(attribute_['ownedComment']['body'])
                            elif parameter == 'type':
                                parameter_type = attribute_['type']

                                if 'PrimitiveType' in parameter_type['@xmi:type']:
                                    primitive_type_url = parameter_type['@href']
                                    url_parts = urlparse(primitive_type_url)
                                    new_attribute.set_type_name(url_parts.fragment)

                            else:
                                constraint_contents = attribute_[parameter]
                                constraint_type = constraint_contents['@xmi:type']

                                if '@value' in constraint_contents:
                                    my_constraint = MyConstraint(parameter,
                                                                 constraint_type,
                                                                 constraint_contents['@value'])
                                else:
                                    my_constraint = MyConstraint(parameter, constraint_type)

                                new_attribute.add_constraint(my_constraint)

                    my_attributes.append(new_attribute)
                    new_attribute = None
                else:
                    print "-------> Unknown attribute type (not property but %s)" % (attribute_['@xmi:type'])

        if new_attribute is None:
            pass
        else:
            my_attributes.append(new_attribute)

        return my_attributes

    def resolve_many_constraints(self):
        for attribute_ in self.attributes:
            if attribute_.has_many_constraint() :
                # print "%s has an attribute with a many constraint at %s : %s" % (self.class_name, attribute_.name, attribute_.type_name)

                # So this is a list type
                # First create a list type name by adding List to the end of the attribute type name
                new_list_name = "ListOf" + attribute_.type_name + "s"

                # And check whether it already exists, if so point the attribute type to the list instead of list item type
                list_type_id = find_id_for_type_name(new_list_name)

                old_attribute_type_id = attribute_.type_id
                old_attribute_type_name = attribute_.type_name
                if list_type_id:
                    # print "Rewriting existing base type information to new list type %s (id=%s)" % (new_list_name, list_type_id)
                    attribute_.set_type_id(list_type_id)
                    attribute_.set_type_name(new_list_name)
                else:
                    # If not, increase the last added type id
                    global last_added_list_type_id
                    last_added_list_type_id += 1
                    # Create a Class representing the new list type with the newly increased id
                    # print "Creating new class %s at id %d" % (new_list_name, last_added_list_type_id)
                    list_class = MyClass()
                    list_class.set_name(new_list_name)
                    list_class.class_id = str(last_added_list_type_id)
                    # The primary ID will be added automatically, but need to add a name column to the list
                    # and a link back from the original type to the list
                    attributes = []
                    new_attribute = MyAttribute()
                    new_attribute.set_name(new_list_name.lower() + "_name")
                    #new_attribute.set_id(old_attribute_id)
                    # Find the type_id for "String"
                    string_type_id = find_id_for_type_name('String')
                    if string_type_id:
                        new_attribute.set_type_id(string_type_id)
                        attributes.append(new_attribute)
                        list_class.attributes = attributes
                        # Save the new class
                        class_ids[list_class.class_id] = new_list_name
                        my_classes.append(list_class)

                        # So a new "list" class has been created, but now the contents need to be made part of this list
                        # The will receive a reference to this list. So each instance of the original type of this
                        # attribute is "part" of a list

                        old_attribute_class = find_class_or_type(old_attribute_type_id)

                        if old_attribute_class:
                            # Add the list as an attrbute to the old type
                            new_attribute = MyAttribute()
                            new_attribute.set_name(new_list_name.lower())
                            new_attribute.set_type_id(list_class.class_id)
                            if isinstance(old_attribute_class, MyClass):
                                old_attribute_class.attributes.append(new_attribute)
                            elif isinstance(old_attribute_class, MyEnumerationType):
                                print "Can't add a new thing to an ENUM list"
                            else:
                                old_attribute_class.attributes.append(new_attribute)
                        else:
                            print "Can't find the class (%s) to add a new link to the list to" % (old_attribute_type_name)

                    else :
                        print "Can't find type ID for STRING, this shouldn't happen"


                    # And point the current attribute to the list
                    # print "Finally setting attribute %s type from %s to %s" % (attribute_.name, attribute_.type_id, list_class.class_id)
                    attribute_.set_type_id(list_class.class_id)


def parse_class_objects(elements):
    for element_ in elements:
        my_class = MyClass(element_)

        my_classes.append(my_class)


class MyEnumerationType:
    def __init__(self, enum_type):
        self.type_id = enum_type['@xmi:id']
        self.name = convert_camel_case(enum_type['@name'])
        type_ids[self.type_id] = self.name

        if 'ownedComment' in enum_type:
            self.comment = enum_type['ownedComment']['body']
        else:
            self.comment = None

        self.literals = dict()

        if 'ownedLiteral' in enum_type:
            for literal in enum_type['ownedLiteral']:
                comment = None
                if isinstance(literal, basestring):
                    my_literal = enum_type['ownedLiteral']
                    literal_name = my_literal['@name']
                    if 'ownedComment' in my_literal:
                        comment = my_literal['ownedComment']['body']
                else:
                    literal_name = literal['@name']
                    if 'ownedComment' in literal:
                        comment = literal['ownedComment']['body']

                self.literals[literal_name] = comment

    def resolve_type_ids(self):
        # No need to resolve unique IDs within an ENUM. They don't have attributes that point to other types
        pass

    def __repr__(self):
        result = "# " + self.name + "\n"

        if self.comment:
            width = 79
            comment = textwrap.fill(self.comment, width=width,
                                    initial_indent='# ',
                                    subsequent_indent='# ')
            result += comment

        result += "# \n"

        for literal in self.literals:
            if self.literals[literal]:
                result += "#    " + literal + " - " + self.literals[literal] + "\n"
            else:
                result += "#    " + literal + "\n"

        result += self.name + " = ("

        first = True
        for literal in self.literals:
            if first:
                result += "\"" + literal + "\""
                first = False
            else:
                result += ", \"" + literal + "\""

        result += ")\n"

        return result.encode('ascii', 'ignore')


def parse_type_enumeration(type_enum):
    my_types.append(MyEnumerationType(type_enum))


class MyDataType:
    def __init__(self, data_type):
        self.output = True
        self.set_name(data_type['@name'])
        self.type_id = data_type['@xmi:id']
        type_ids[self.type_id] = self.name

        if 'ownedComment' in data_type:
            self.comment = data_type['ownedComment']['body']
        else:
            self.comment = None

        self.attributes = []
        self._parse_attributes(data_type)

    def resolve_type_ids(self):
        for attribute_ in self.attributes:
            attribute_.resolve_type_ids()

    def set_name(self, name):
        """Set the name of this class. Some classes are really just aliases of base types. Those
        have their name rewritten to a base SQLAlchemy type. Also their output is set to False so they are not
        printed when repr is called
        """
        if name == 'PositiveInteger' :
            self.name = 'Integer'
            self.output = False
        elif name == 'NaturalNumber' :
            self.name = 'Integer'
            self.output = False
        elif name == 'TimeAndDate' :
            self.name = 'DateTime'
            self.output = False
        elif name == 'Real' :
            self.name = 'Float'
            self.output = False
        elif name == 'Percentage':
            self.name = 'Float'
            self.output = False
        elif name == 'Identifier45':
            self.name = 'String'
            self.length = 45
            self.output = False
        elif name == 'Identifier90':
            self.name = 'String'
            self.length = 90
            self.output = False
        else :
            # print "Not converting %s to base type" % (name)
            self.name = name


    def parse_attribute(self, attribute_):
        new_attribute = MyAttribute()

        new_attribute.set_name(attribute_['@name'])
        new_attribute.set_id(attribute_['@xmi:id'])
        if '@type' in attribute_:
            new_attribute.set_type_id(attribute_['@type'])

        for parameter in attribute_:
            if not parameter.startswith('@'):
                if parameter == 'ownedComment':
                    new_attribute.set_comment(attribute_['ownedComment']['body'])
                elif parameter == 'type':
                    parameter_type = attribute_['type']

                    if 'PrimitiveType' in parameter_type['@xmi:type']:
                        primitive_type_url = parameter_type['@href']
                        url_parts = urlparse(primitive_type_url)
                        new_attribute.set_type_name(url_parts.fragment)

                else:
                    constraint_contents = attribute_[parameter]
                    constraint_type = constraint_contents['@xmi:type']

                    if '@value' in constraint_contents:
                        my_constraint = MyConstraint(parameter,
                                                     constraint_type,
                                                     constraint_contents['@value'])
                    else:
                        my_constraint = MyConstraint(parameter, constraint_type)

                    new_attribute.add_constraint(my_constraint)

        self.attributes.append(new_attribute)

    def _parse_attributes(self, attributes):
        for attribute_, attribute_items in attributes.iteritems():
            if isinstance(attributes[attribute_], basestring):
                # The strings found here are those we've used before
                pass
            else:
                # Only interested in ownedAttribute attributes
                if attribute_ == 'ownedAttribute':
                    if isinstance(attribute_items, dict):
                        self.parse_attribute(attribute_items)
                    else:
                        for attribute_item in attribute_items:
                            self.parse_attribute(attribute_item)

    def __repr__(self):

        # Don't output anything when output is set to false
        if not self.output:
            return ""

        result = "class "
        # if self.general_class_id:
        #     if self.general_class_name:
        #         result += self.class_name + " (" + self.general_class_name + ")"
        #     else:
        #         result += self.class_name + " (" + self.general_class_id + ")"
        # else:
        result += self.name

        result += "(Base): # datatype definition\n"

        result += "    __tablename__ = \'" + self.name.lower() + "\'\n\n"

        result += "    id = Column(Integer, primary_key=True)"

        # if self.is_abstract:
        #     result += "  # Abstract"

        # result += " " + self.class_id

        if len(self.attributes) > 0:
            for attribute_ in self.attributes:
                result += "\n"
                result += repr(attribute_)
        else:
            result += "\n        pass\n"

        result += "\n"

        return result.encode('ascii', 'ignore')


def parse_type_data(data_type):
    my_types.append(MyDataType(data_type))


def parse_type_definitions(elements):
    # print(json.dumps(elements, indent=4))

    for element in elements:
        if element['@xmi:type'] == 'uml:Enumeration':
            parse_type_enumeration(element)
            success = True
        elif element['@xmi:type'] == 'uml:DataType':
            parse_type_data(element)
            success = True
        else:
            print(json.dumps(element, indent=4))
            success = False
            pass

        if not success:
            break


def parse_associations(elements):
    # print(json.dumps(elements, indent=4))
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", type=string, help="UML XML file to parse")
    parser.add_argument("outfile", type=string, help="Name of the output Python file")
    args = parser.parse_args()

    infile = args.infile
    outfile = args.outfile

    with open(infile) as fd, open(outfile, 'a') as fw:
        doc = xmltodict.parse(fd.read())
        # print(json.dumps(doc, indent=4))

        xmi = doc['xmi:XMI']
        package = xmi['uml:Package']

        # print "\"\"\"Package name = %s" % package['@name']

        package_elements = package['packagedElement']

        for element in package_elements:
            element_name = element['@name']
            # print "Now in package element %s" % element_name

            if element_name == 'TypeDefinitions':
                parse_type_definitions(element['packagedElement'])
                #pass

        for element in package_elements:
            element_name = element['@name']
            # print "Now in package element %s" % element_name

            if element_name == 'ObjectClasses':
                parse_class_objects(element['packagedElement'])
                pass

        for element in package_elements:
            element_name = element['@name']
            # print "Now in package element %s" % element_name

            if element_name == 'Associations':
                parse_associations(element['packagedElement'])

        # print "\"\"\"\n\n"

        fw.write("""from sqlalchemy.ext.declarative import declarative_base
    Base = declarative_base()
    from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Boolean, ForeignKey
    
        """)


        for class_ in my_classes:
            class_.resolve_type_ids()

        for type_ in my_types:
            type_.resolve_type_ids()

        # print "Resolving x to many constraints"

        for class_ in my_classes:
            class_.resolve_many_constraints()

        # print "Done resolving x to many constraints"

        for class_ in my_classes:
            class_.resolve_type_ids()

        for type_ in my_types:
            type_.resolve_type_ids()



        for type_ in my_types:
            if isinstance(type_, MyEnumerationType) :
                fw.write(repr(type_))

        fw.write("\n")

        for type_ in my_types:
            if not isinstance(type_, MyEnumerationType) :
                fw.write(repr(type_))

        for class_ in my_classes:
            # class_.resolve_type_ids()

            #if not class_.is_abstract:
            fw.write(repr(class_))

