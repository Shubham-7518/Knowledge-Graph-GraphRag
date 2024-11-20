import json
import os
from flask import Flask, make_response, jsonify, render_template,request
from neo4j import GraphDatabase
from flask_cors import CORS
import graphrag
from groq import Groq
from fuzzywuzzy import fuzz
from sentence_transformers import SentenceTransformer
import numpy as np
import re


app = Flask(__name__)

CORS(app, origins="http://localhost:4200")
# Neo4j connection setup
uri = "bolt://localhost:7687"  # Adjust if necessary
driver = GraphDatabase.driver(uri, auth=("neo4j", "1234567890"))  # Replace with your password


client = Groq(api_key="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")

candidate_labels = ["Project", "Tag", "Technology", "Sustainability", "Company", "Phase", "Factory", "Brand"]

# Define the path to your JSON files
files = ['json_data/oip-db.user.json', 'json_data/oip-db.university.json' ,'json_data/oip-db.sustainability.json'
         ,'json_data/oip-db.projectPhases.json' ,'json_data/oip-db.project.json' ,'json_data/oip-db.factory.json', 'json_data/oip-db.company.json']


def load_json_files():
    data = {}
    for file_path in files:
        try:
            with open(file_path, 'r') as file:
                loaded_data = json.load(file)
                data[file_path] = loaded_data  # Store data by file name
        except Exception as e:
            print("Error loading " + file_path + ": " + str(e))

    return data

@app.route('/data', methods=['GET'])
def get_data():
    data = load_json_files()
    return jsonify(data)

#@app.route('/test-query', methods=['GET'])
#def test_query():
#    try:
#        with driver.session() as session:
#            result = session.run("MATCH (n) RETURN COUNT(n) AS nodeCount")
#            count = result.single()['nodeCount']
#        return jsonify({"nodeCount": count}), 200
#    except Exception as e:
#        return jsonify({"error": str(e)}), 500

@app.route('/check-neo4j', methods=['GET'])
def check_neo4j_connection():
    try:
        with driver.session() as session:
            session.run("RETURN 1")
        return jsonify({"message": "Connected to Neo4j successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


#Shubham wala code

def node_to_dict(node):
    return {
        'id': node.id,
        'labels': list(node.labels),  
        'properties': dict(node.items()) 
    }


def relationship_to_dict(relationship):
    return {
        'id': relationship.id,
        'type': relationship.type,
        'properties': dict(relationship.items()) 
    }


def fetch_graph_data():
    with driver.session() as session:
        query = """
        MATCH (n)-[r]->(m)
        RETURN n, r, m
        """
        result = session.run(query)
        data = []
        for record in result:
            data.append({
                'node1': node_to_dict(record['n']),
                'relationship': relationship_to_dict(record['r']),
                'node2': node_to_dict(record['m']),
            })
        return data
    
@app.route('/graph_data', methods=['GET'])
def get_graph():
    graph_data = fetch_graph_data()
    return jsonify(graph_data)



# Function to generate Cypher query with a general prompt
def text_to_cypher(text_query):

    query_patterns = {
        'brand': r'\bbrand\b\s*(?:\'|")?(\w+)(?:\'|")?',  # Match 'brand' followed by the brand name, allowing optional quotes
        'phase': r'\bphase\b\s*(?:\'|")?([\w\s]+)(?:\'|")?',  # Match 'phase' followed by the phase number
        'company': r'\bcompany\b\s*(?:\'|")?([\w\s]+)(?:\'|")?',  # Match 'company' followed by company name, allowing optional quotes
        'technology_trend': r'\btechnology\b\s*(?:\'|")?([\w\s]+)(?:\'|")?'  # Match 'technology' followed by the trend name, allowing optional quotes
    }

    brand = None
    phase = None
    company = None
    technology_trend = None

    # Check for each keyword in the user query and extract the value
    for key, pattern in query_patterns.items():
        match = re.search(pattern, text_query)
        if match:
            if key == 'brand':
                brand = match.group(1)
            elif key == 'phase':
                phase = match.group(1)
            elif key == 'company':
                company = match.group(1)
            elif key == 'technology_trend':
                technology_trend = match.group(1)

    # Now construct the Cypher query based on the detected parameters
    cypher_query = "MATCH (p:Project)"
    
    # Add filters for the relationships
    filters = []
    
    if brand:
        cypher_query += "-[:HAS_BRAND]->(b:Brand)"
        filters.append(f"b.name = '{brand}'")
    if phase:
        cypher_query += "-[:HAS_Phase]->(ph:Phase)"
        filters.append(f"ph.name = '{phase}'")
    if company:
        cypher_query += "-[:HAS_COMPANY]->(c:Company)"
        filters.append(f"c.companyName CONTAINS '{company}'")
    if technology_trend:
        cypher_query += "-[:HAS_TECHNOLOGY_TREND]->(t:TechnologyTrend)"
        filters.append(f"t.name CONTAINS '{technology_trend}'")
    
    # Combine the filters
    if filters:
        cypher_query += " WHERE " + " AND ".join(filters)
    
    # Return the final Cypher query
    cypher_query += " RETURN p.projectName, p.technologyTrend, p.overview"
    
    return cypher_query


    # text_query = text_query+" - generate specific cypher query query only, provide me the cypher query only i don't want extra text. Reference schema is"+schema

    # chat_completion = client.chat.completions.create(
    # messages=[
    #     {
    #         "role": "user",
    #         "content": text_query,
    #     }
    # ],
    # model="llama3-8b-8192",
    # )
    # return chat_completion.choices[0].message.content


def modify_response(graph_data,user_question):
    graph_data_str = str(graph_data)

    text_query = user_question+" User asked this question and the answer of the question is "+graph_data_str+" Convert this into natural language. But don't mention that you have converted the response into natural language. Beautify the response with some markdowns.Exclude duplicate projects.And keep the project name as it is"
    # text_query = graph_data_str+" Convert this into a natural language understandable by humans, the question asked by the user is "+user_question

    chat_completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": text_query,
        }
    ],
    model="llama3-8b-8192",
    )
    return chat_completion.choices[0].message.content

# Function to execute a Cypher query on Neo4j
def execute_cypher_query(cypher_query):
    with driver.session() as session:
        result = session.run(cypher_query)
        return [record for record in result]
    





# Endpoint to process user query
@app.route('/ask', methods=['POST'])
def ask():
    user_query = request.json.get('query')
    
    generated_cypher = text_to_cypher(user_query)
    
    print(generated_cypher)

    results= execute_cypher_query(generated_cypher)
    modified_response = modify_response(results,user_query)
    # Generate a summary of the results

    
    return jsonify({
        "query": user_query,
        "cypher_query": user_query,
        "results": modified_response
    })

#Shubham wala code end







@app.route('/load-data', methods=['POST'])
def load_data():
    data = load_json_files()
    if not data:
        return jsonify({"error": "No data loaded from JSON files."}), 400

    with driver.session() as session:
        try:
            # Insert User and their attributes as separate nodes (unchanged)
            user_data = data.get('json_data/oip-db.user.json', [])
            for user in user_data:
                user_name = user.get('name')
                user_id = user.get('userId')

                # Create user node
                session.run(
                    """
                    MERGE (u:User {userId: $userId})
                    SET u.name = $name
                    """,
                    userId=user_id,
                    name=user_name
                )

                # Create brand node and relationship
                brand = user.get('brand')
                if brand:
                    session.run(
                        """
                        MERGE (b:Brand {name: $brand})
                        MERGE (u:User {userId: $userId})
                        MERGE (u)-[:HAS_BRAND]->(b)
                        """,
                        brand=brand,
                        userId=user_id
                    )

                # Create department node and relationship
                department = user.get('department')
                if department:
                    session.run(
                        """
                        MERGE (d:Department {name: $department})
                        MERGE (u:User {userId: $userId})
                        MERGE (u)-[:HAS_DEPARTMENT]->(d)
                        """,
                        department=department,
                        userId=user_id
                    )

                # Create email node and relationship
                email = user.get('email')
                if email:
                    session.run(
                        """
                        MERGE (e:Email {Email: $email})
                        MERGE (u:User {userId: $userId})
                        MERGE (u)-[:HAS_EMAIL]->(e)
                        """,
                        email=email,
                        userId=user_id
                    )


                # Create active status node (if necessary)
                active = user.get('active')
                if active is not None:
                    session.run(
                        """
                        MERGE (a:ActiveStatus {status: $active})
                        MERGE (u:User {userId: $userId})
                        MERGE (u)-[:HAS_ACTIVE_STATUS]->(a)
                        """,
                        active=active,
                        userId=user_id
                    )
                    
           # Insert University data and attributes as separate nodes
            university_data = data.get('json_data/oip-db.university.json', [])
            for university in university_data:
                id_code = university.get('idCode')
                university_id = university.get('_id', {}).get('$oid')
                
                # Create university node
                session.run(
                    """
                    MERGE (un:University {idCode: $idCode})
                    SET un.name = $name,
                        un.overview = $overview,
                        un.address = $address,
                        un.website = $website,
                        un.ranking = $ranking,
                        un.state = $state,
                        un.city = $city,
                        un.country = $country,
                        un.studentsCount = $studentsCount,
                        un.notes = $notes,
                        un.universityId =$universityId
                    """,
                    idCode=id_code,
                    universityId=university_id,
                    name=university.get('name'),
                    overview=university.get('overview'),
                    address=university.get('address'),
                    website=university.get('website'),
                    ranking=university.get('ranking'),
                    state=university.get('state'),
                    city=university.get('city'),
                    country=university.get('country'),
                    createdByName=university.get('createdByName'),
                    studentsCount=university.get('studentsCount'),
                    notes=university.get('notes')
                )

               # Create brand node and relationship
                brand = university.get('brand')
                if brand:
                    session.run(
                        """
                        MERGE (b:Brand {name: $brand})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_BRAND]->(b)
                        """,
                        brand=brand,
                        idCode=id_code
                    )



                # Create id node and relationship
                id = university.get('_id', {}).get('$oid')
                if id:
                    session.run(
                        """
                        MERGE (b:Id {name: $id})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_UNIVERSITY_ID]->(b)
                        """,
                        id=id,
                        idCode=id_code
                    )
                    # Create state node and relationship
                state = university.get('state')
                if state:
                    session.run(
                        """
                        MERGE (b:State {name: $state})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_STATE]->(b)
                        """,
                        state=state,
                        idCode=id_code
                    )

                    # Create city node and relationship
                city = university.get('city')
                if city:
                    session.run(
                        """
                        MERGE (b:City {name: $city})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_CITY]->(b)
                        """,
                        city=city,
                        idCode=id_code
                    )

                    # Create country node and relationship
                country = university.get('country')
                if country:
                    session.run(
                        """
                        MERGE (b:Country {name: $country})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_COUNTRY]->(b)
                        """,
                        country=country,
                        idCode=id_code
                    )
                # Create department node and relationship
                department = university.get('department')
                if department:
                    session.run(
                        """
                        MERGE (d:Department {name: $department})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_DEPARTMENT]->(d)
                        """,
                        department=department,
                        idCode=id_code
                    )

                # Create contact node and relationship
                contact_name = university.get('contactName')
                if contact_name:
                    session.run(
                        """
                        MERGE (c:Contact {name: $contactName})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_CONTACT]->(c)
                        """,
                        contactName=contact_name,
                        idCode=id_code
                    )

                # Create email node and relationship
                email = university.get('email')
                if email:
                    session.run(
                        """
                        MERGE (e:Email {address: $email})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_EMAIL]->(e)
                        """,
                        email=email,
                        idCode=id_code
                    )

                # Create tags nodes and relationships
                tags = university.get('tags', [])
                for tag in tags:
                    session.run(
                        """
                        MERGE (t:Tag {name: $tag})
                        MERGE (un:University {idCode: $idCode})
                        MERGE (un)-[:HAS_TAG]->(t)
                        """,
                        tag=tag,
                        idCode=id_code
                    )
           # Insert Sustainability data and attributes as separate nodes
            sustainability_data = data.get('json_data/oip-db.sustainability.json', [])
            for sustainability in sustainability_data:
                id_code = sustainability.get('_id', {}).get('$oid')  # Extracting the unique ID
                sustainability_id = sustainability.get('_id', {}).get('$oid')
            
                # Create sustainability node
                session.run(
                    """
                    MERGE (s:Sustainability {idCode: $idCode})
                    SET s.name = $name,
                        s.createdBy = $createdBy,
                        s.createdOn = $createdOn,
                        s.modifiedBy = $modifiedBy,
                        s.modifiedOn = $modifiedOn,
                        s.sustainabilityId= $sustainabilityId
                    """,
                    idCode=id_code,
                    name=sustainability.get('name'),
                    brand=sustainability.get('brand'),
                    sustainabilityId=sustainability_id,
                    createdBy=sustainability.get('createdBy'),
                    createdOn=sustainability.get('createdOn', {}).get('$date'),  # Assuming date needs to be formatted
                    modifiedBy=sustainability.get('modifiedBy'),
                    modifiedOn=sustainability.get('modifiedOn', {}).get('$date')  # Assuming date needs to be formatted
                )
            
                # Create brand node and relationship (if not already handled in the sustainability node creation)
                brand = sustainability.get('brand')
                if brand:
                    session.run(
                        """
                        MERGE (b:Brand {name: $brand})
                        MERGE (s:Sustainability {idCode: $idCode})
                        MERGE (s)-[:HAS_BRAND]->(b)
                        """,
                        brand=brand,
                        idCode=id_code
                    )
            
    # Insert Company data and attributes as separate nodes
            company_data = data.get('json_data/oip-db.company.json', [])
            for company in company_data:
                id_code = company.get('_id', {}).get('$oid')  # Extracting the unique ID
                company_id = company.get('_id', {}).get('$oid')
                
                # Create company node
                session.run(
                    """
                    MERGE (c:Company {idCode: $idCode})
                    SET c.companyName = $companyName,
                        c.companyId = $companyId,
                        c.companyid = $companyid,
                        c.website = $website,
                        c.address = $address,
                        c.description = $description,
                        c.notes = $notes,
                        c.founders = $founders,
                        c.foundingYear = $foundingYear,
                        c.ownerContact = $ownerContact,
                        c.initiator = $initiator,
                        c.stage = $stage,
                        c.alsoInContactWith = $alsoInContactWith,
                        c.informationSource = $informationSource,
                        c.initialContactDate = $initialContactDate,
                        c.trl = $trl,
                        c.mrl = $mrl,
                        c.status = $status,
                        c.phase = $phase,
                        c.createdBy = $createdBy,
                        c.createdOn = $createdOn,
                        c.modifiedBy = $modifiedBy,
                        c.modifiedOn = $modifiedOn
                    """,
                    idCode=id_code,
                    companyName=company.get('companyName'),
                    companyId= company_id,
                    companyid=company.get('companyId'),
                    website=company.get('website'),
                    category=company.get('category'),
                    address=company.get('address'),
                    city=company.get('city'),
                    state=company.get('state'),
                    country=company.get('country'),
                    description=company.get('description'),
                    notes=company.get('notes'),
                    productService=company.get('productService'),
                    founders=company.get('founders'),
                    foundingYear=company.get('foundingYear'),
                    createdByName=company.get('createdByName'),
                    ownerContact=company.get('ownerContact'),
                    initiator=company.get('initiator'),
                    department=company.get('department'),
                    sharedWith=company.get('sharedWith'),
                    stage=company.get('stage'),
                    alsoInContactWith=company.get('alsoInContactWith'),
                    informationSource=company.get('informationSource'),
                    initialContactDate=company.get('initialContactDate'),
                    trl=company.get('trl'),
                    mrl=company.get('mrl'),
                    status=company.get('status'),
                    phase=company.get('phase'),
                    createdBy=company.get('createdBy'),
                    createdOn=company.get('createdOn', {}).get('$date'),  # Assuming date needs to be formatted
                    modifiedBy=company.get('modifiedBy'),
                    modifiedOn=company.get('modifiedOn', {}).get('$date')  # Assuming date needs to be formatted
                )
                
                # Create brand node and relationship
                brand = company.get('brand')
                if brand:
                    session.run(
                        """
                        MERGE (b:Brand {name: $brand})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_BRAND]->(b)
                        """,
                        brand=brand,
                        idCode=id_code
                    )

                # Create sharedWith node and relationship
                sharedWith = company.get('sharedWith')
                if sharedWith:
                    session.run(
                        """
                        MERGE (b:SharedWith {name: $sharedWith})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_SHARED_WITH]->(b)
                        """,
                        sharedWith=sharedWith,
                        idCode=id_code
                    )

                # Create sharedWith node and relationship
                department = company.get('department')
                if department:
                    session.run(
                        """
                        MERGE (b:Department {name: $department})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_DEPARTMENT]->(b)
                        """,
                        department=department,
                        idCode=id_code
                    )

                # Create productService node and relationship
                productService = company.get('productService')
                if productService:
                    session.run(
                        """
                        MERGE (b:ProductService {name: $productService})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_PRODUCT_SERVICE]->(b)
                        """,
                        productService=productService,
                        idCode=id_code
                    )


                 # Create city node and relationship
                city = company.get('city')
                if city:
                    session.run(
                        """
                        MERGE (b:City {name: $city})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_CITY]->(b)
                        """,
                        city=city,
                        idCode=id_code
                    )

                 # Create category node and relationship
                category = company.get('category')
                if category:
                    session.run(
                        """
                        MERGE (b:Category {name: $category})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_CATEGORY]->(b)
                        """,
                        category=category,
                        idCode=id_code
                    )
                    
                # Create state node and relationship
                state = company.get('state')
                if state:
                    session.run(
                        """
                        MERGE (b:State {name: $state})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_STATE]->(b)
                        """,
                        state=state,
                        idCode=id_code
                    )

                # Create country node and relationship
                country = company.get('country')
                if country:
                    session.run(
                        """
                        MERGE (b:Country {name: $country})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_COUNTRY]->(b)
                        """,
                        country=country,
                        idCode=id_code
                    )


                # Create tags nodes and relationships
                tags = company.get('tags', [])
                for tag in tags:
                    session.run(
                        """
                        MERGE (t:Tag {name: $tag})
                        MERGE (c:Company {idCode: $idCode})
                        MERGE (c)-[:HAS_TAG]->(t)
                        """,
                        tag=tag,
                        idCode=id_code
                    )
                
                # Create stakeholder nodes and relationships
                stakeholders = company.get('stakeholder', [])
                for stakeholder in stakeholders:
                    stakeholder_name = stakeholder.get('name')
                    if stakeholder_name:
                        session.run(
                            """
                            MERGE (s:Stakeholder {name: $name})
                            MERGE (c:Company {idCode: $idCode})
                            MERGE (c)-[:HAS_STAKEHOLDER]->(s)
                            """,
                            name=stakeholder_name,
                            idCode=id_code
                        )


                        # Insert Factory data and attributes as separate nodes
            factory_data = data.get('json_data/oip-db.factory.json', [])
            for factory in factory_data:
                id_code = factory.get('_id', {}).get('$oid')  # Extracting the unique ID
                factory_id = factory.get('_id', {}).get('$oid')
                
                # Create factory node
                session.run(
                    """
                    MERGE (f:Factory {idCode: $idCode})
                    SET f.name = $name,
                        f.factoryid = $factoryid,
                        f.brand = $brand,
                        f.createdBy = $createdBy,
                        f.createdOn = $createdOn,
                        f.modifiedBy = $modifiedBy,
                        f.modifiedOn = $modifiedOn,
                        f.factoryId = $factoryId
                    """,
                    idCode=id_code,
                    name=factory.get('name'),
                    factoryId=factory_id,
                    factoryid=factory.get('factoryId'),
                    brand=factory.get('brand'),
                    createdBy=factory.get('createdBy'),
                    createdOn=factory.get('createdOn', {}).get('$date'),  # Assuming date needs to be formatted
                    modifiedBy=factory.get('modifiedBy'),
                    modifiedOn=factory.get('modifiedOn', {}).get('$date')  # Assuming date needs to be formatted
                )
            
                # Create brand node and relationship
                brand = factory.get('brand')
                if brand:
                    session.run(
                        """
                        MERGE (b:Brand {name: $brand})
                        MERGE (f:Factory {idCode: $idCode})
                        MERGE (f)-[:HAS_BRAND]->(b)
                        """,
                        brand=brand,
                        idCode=id_code
                    )
            # Insert Sustainability data and attributes as separate nodes
            projectphase_data = data.get('json_data/oip-db.projectPhases.json', [])
            for phase in projectphase_data:
                id_code = phase.get('_id')  # Extracting the unique ID
                phase_id = phase.get('_id')
            
                # Create projrctphase node
                session.run(
                    """
                    MERGE (d:Phase {idCode: $idCode})
                    SET d.name = $name,
                        d.phase = $phase,
                        d.createdBy = $createdBy,
                        d.createdOn = $createdOn,
                        d.modifiedBy = $modifiedBy,
                        d.modifiedOn = $modifiedOn,
                        d.phaseId=$phaseId
                    """,
                    idCode=id_code,
                    name=phase.get('name'),
                    phaseId=phase_id,
                    brand=phase.get('brand'),
                    phase=phase.get('phase'),
                    createdBy=phase.get('createdBy'),
                    createdOn=phase.get('createdOn', {}).get('$date'),  # Assuming date needs to be formatted
                    modifiedBy=phase.get('modifiedBy'),
                    modifiedOn=phase.get('modifiedOn', {}).get('$date')  # Assuming date needs to be formatted
                )


                # Create brand node and relationship
                brand = phase.get('brand')
                if brand:
                    session.run(
                        """
                        MERGE (b:Brand {name: $brand})
                        MERGE (f:Phase {idCode: $idCode})
                        MERGE (f)-[:HAS_BRAND]->(b)
                        """,
                        brand=brand,
                        idCode=id_code
                    )

                  # Insert Project data and attributes as separate nodes
            project_data = data.get('json_data/oip-db.project.json', [])
            for project in project_data:
                id_code = project.get('_id', {}).get('$oid')  # Extracting the unique ID
                project_id = project.get('_id', {}).get('$oid')  # Extracting the project ID
                university_id = project.get('university', {}).get('$oid')
                sustainability_id = project.get('sustainability',{}).get('$oid')
                phase_id=project.get('phase')
                factory_id=project.get('factoryLocation', {}).get('$oid')
                company_id=project.get('startups', {}).get('$oid')
                
                # Create project node
                session.run(
                    """
                    MERGE (p:Project {idCode: $idCode})
                    SET p.projectName = $projectName,
                        p.overview = $overview,
                        p.technologyTrend = $technologyTrend,
                        p.responsible = $responsible,
                        p.link = $link,
                        p.phase = $phaseId,
                        p.contactName = $contactName,
                        p.contactDepartment = $contactDepartment,
                        p.contactEmail = $contactEmail,
                        p.remarks = $remarks,
                        p.risks = $risks,
                        p.brand = $brand,
                        p.email = $email,
                        p.createdBy = $createdBy,
                        p.createdOn = $createdOn,
                        p.modifiedBy = $modifiedBy,
                        p.modifiedOn = $modifiedOn,
                        p.universityId = $universityId,
                        p.sustainabilityId = $sustainabilityId,
                        p.factoryId = $factoryId,
                        p.companyId = $companyId
                    """,
                    idCode=id_code,
                    projectId=project_id,
                    universityId=university_id,
                    factoryId=factory_id,
                    companyId=company_id,
                    phaseId=phase_id,
                    sustainabilityId=sustainability_id,
                    projectName=project.get('projectName'),
                    overview=project.get('overview'),
                    technologyTrend=project.get('technologyTrend'),
                    responsible=project.get('responsible'),
                    link=project.get('link'),
                    phase=project.get('phase'),
                    contactName=project.get('contactName'),
                    contactDepartment=project.get('contactDepartment'),
                    contactEmail=project.get('contactEmail'),
                    remarks=project.get('remarks'),
                    risks=project.get('risks'),
                    brand=project.get('brand'),
                    email=project.get('email'),
                    createdBy=project.get('createdBy'),
                    createdOn=project.get('createdOn', {}).get('$date'),  # Assuming date needs to be formatted
                    modifiedBy=project.get('modifiedBy'),
                    modifiedOn=project.get('modifiedOn', {}).get('$date')  # Assuming date needs to be formatted
                )

                # Create technologyTrend node and relationship
                technologyTrend=project.get('technologyTrend')
                if technologyTrend:
                    session.run(
                        """
                        MERGE (b:TechnologyTrend {name: $technologyTrend})
                        MERGE (p:Project {idCode: $idCode})
                        MERGE (p)-[:HAS_TECHNOLOGY_TREND]->(b)
                        """,
                        technologyTrend=technologyTrend,
                        idCode=id_code
                    )

                # Create brand node and relationship
                brand=project.get('brand')
                if brand:
                    session.run(
                        """
                        MERGE (b:Brand {name: $brand})
                        MERGE (p:Project {idCode: $idCode})
                        MERGE (p)-[:HAS_BRAND]->(b)
                        """,
                        brand=brand,
                        idCode=id_code
                    )
                   
               # Check if the university exists and create the relationship
                if university_id:  # Check if university_id is available
                   session.run(
                       """
                       MATCH (un:University {universityId: $universityId}),
                             (p:Project {idCode: $projectId})
                       MERGE (un)-[:HAS_PROJECT]->(p)
                       """,
                       universityId=university_id,
                       projectId=project_id
                   )

                                  # Check if the company exists and create the relationship
                if company_id:  # Check if company_id is available
                   session.run(
                       """
                       MATCH (un:Company {companyId: $companyId}),
                             (p:Project {idCode: $projectId})
                       MERGE (p)-[:HAS_COMPANY]->(un)
                       """,
                       companyId=company_id,
                       projectId=project_id
                   )

                # Check if the sustainability exists and create the relationship
                if sustainability_id:  
                   session.run(
                       """
                       MATCH (un:Sustainability {sustainabilityId: $sustainabilityId}),
                             (p:Project {idCode: $projectId})
                       MERGE (p)-[:HAS_SUSTAINABILITY]->(un)
                       """,
                       sustainabilityId=sustainability_id,
                       projectId=project_id
                   )
                # Check if the factory exists and create the relationship
                if factory_id:  
                   session.run(
                       """
                       MATCH (un:Factory {factoryId: $factoryId}),
                             (p:Project {idCode: $projectId})
                       MERGE (p)-[:HAS_FACTORY]->(un)
                       """,
                       factoryId=factory_id,
                       projectId=project_id
                   )

                # Check if the phase exists and create the relationship
                if phase_id:  
                   session.run(
                       """
                       MATCH (un:Phase {phaseId: $phaseId}),
                             (p:Project {idCode: $projectId})
                       MERGE (p)-[r:HAS_Phase]->(un)
                       ON CREATE SET r.createdOn = timestamp()
                       """,
                       phaseId=phase_id,
                       projectId=project_id
                   )
                   
                                                   
               
                


            
                # Create tags nodes and relationships
                tags = project.get('tags', [])
                for tag in tags:
                    session.run(
                        """
                        MERGE (t:Tag {name: $tag})
                        MERGE (p:Project {idCode: $idCode})
                        MERGE (p)-[:HAS_TAG]->(t)
                        """,
                        tag=tag,
                        idCode=id_code
                    )
            
                # Create published brands relationships
                published_brands = project.get('publishedToBrands', [])
                for published_brand in published_brands:
                    session.run(
                        """
                        MERGE (b:Brand {name: $publishedBrand})
                        MERGE (p:Project {idCode: $idCode})
                        MERGE (p)-[:PUBLISHED_TO]->(b)
                        """,
                        publishedBrand=published_brand,
                        idCode=id_code
                    )

 

                     
            return jsonify({"message": "Data loaded successfully!"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500





#def fetch_data():
#    with driver.session() as session:
#        query = "MATCH (n)-[r]->(m) RETURN n, r, m"
#        result = session.run(query)
#        return list(result)
#
#def create_json_data(data):
#    nodes = []
#    links = []
#    node_set = set()  # To avoid duplicate nodes
#
#    for record in data:
#        node_a = record['n']
#        node_b = record['m']
#        relationship = record['r']
#
#        # Ensure node_a and node_b have a 'name' property
#        if 'name' in node_a and node_a['name'] not in node_set:
#            nodes.append({"id": node_a['name']})  # Adjust based on your node properties
#            node_set.add(node_a['name'])
#        
#        if 'name' in node_b and node_b['name'] not in node_set:
#            nodes.append({"id": node_b['name']})
#            node_set.add(node_b['name'])
#
#        # Ensure the relationship has the needed properties
#        if node_a.get('name') and node_b.get('name'):
#            links.append({"source": node_a['name'], "target": node_b['name'], "label": relationship.type})
#
#    return {"nodes": nodes, "links": links}
#
#@app.route('/')
#def index():
#    data = fetch_data()  # Fetch data from Neo4j
#    json_data = create_json_data(data)  # Create JSON data
#    return render_template('index.html', graph_data=json.dumps(json_data))


def get_tags():
    with driver.session() as session:
        query = """
        MATCH (p:Project)-[:HAS_TAG]->(t:Tag)
        RETURN DISTINCT t.name as name
        """
        result = session.run(query)
        tags = []
        for record in result:
            tags.append({"tag_name": record['name']})  # Ensure it's a dictionary
        return tags

@app.route('/tags', methods=['GET'])
def get_project_tags():
    try:
        tags = get_tags()  # Fetch tags as a list of dictionaries
        return jsonify(tags), 200  # Return tags as JSON
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Function to fetch all projects from Neo4j
def fetch_projects(tx):
    query = """
    MATCH (p:Project)-[:HAS_TAG]->(t:Tag)
    RETURN p.projectName AS projectName, 
       p.overview AS overview, 
       p.technologyTrend AS technologyTrend, 
       COLLECT(t.name) AS tagNames
    """
    result = tx.run(query)
    return list(result)


# Function to calculate similarity score
def calculate_similarity(user_data, db_projects):
    message=''
    similarity_scores = []

    # Check if the project exists in db_projects based on both projectName and technologyTrend
    project_exists = False
    for project in db_projects:
        if (user_data['projectName'].strip().lower() == project['projectName'].strip().lower() and
            user_data['technologyTrend'].strip().lower() == project['technologyTrend'].strip().lower()):
            project_exists = True
            break
    
    # If no matching project is found, return a message
    if not project_exists:
        message= "No matching project found"
    
    # Compare user data to each project from the database
    for project in db_projects:
        project_name = project['projectName']
        project_overview = project['overview']
        project_technology = project['technologyTrend']
        project_tags = project['tagNames']

        # Exact match for project name
        if user_data['projectName'].strip().lower() == project_name.strip().lower():
            name_similarity = 100
        else:
            name_similarity = fuzz.ratio(user_data['projectName'], project_name)

        # Exact match for technology trend
        if user_data['technologyTrend'].strip().lower() == project_technology.strip().lower():
            technology_similarity = 100
        else:
            technology_similarity = fuzz.ratio(user_data['technologyTrend'], project_technology)

        # Fuzzy match for project overview
        if user_data['projectOverview'].strip().lower() == project_overview.strip().lower():
            overview_similarity = 100
        else:
            overview_similarity = fuzz.partial_ratio(user_data['projectOverview'], project_overview)

        # Jaccard similarity for tags (case insensitive)
        tags_similarity = len(set([tag.lower() for tag in user_data['selectedTags']]).intersection(
                                set([tag.lower() for tag in project_tags]))) / len(set([tag.lower() for tag in user_data['selectedTags']]).union(
                                set([tag.lower() for tag in project_tags])))

        # Calculate an overall similarity score (weighted average of the components)
        total_similarity = (name_similarity * 0.1 + 
                            technology_similarity * 0.3 + 
                            overview_similarity * 0.3 + 
                            tags_similarity * 0.3)
        
        total_similarity = round(total_similarity, 2)

        similarity_scores.append({
            'project': project,
            'similarity': total_similarity,
            'message':message
        })
    
    # Sort the projects by similarity score in descending order
    similarity_scores.sort(key=lambda x: x['similarity'], reverse=True)

    # Return the top 2 most similar projects
    return similarity_scores[:2]



@app.route('/match-project', methods=['POST'])
def save_project():
    data = request.json  # Get the data sent from the frontend
    
    with driver.session() as session:
        db_projects = session.execute_read(fetch_projects)
     

    similarity_scores = calculate_similarity(data, db_projects)

    if not data:
        return jsonify({"error": "No data provided"}), 400

    return jsonify(similarity_scores), 200



def fetch_data(tx, appliedFilter):

    if appliedFilter == "" or appliedFilter == "None":
        query = f"""
        MATCH (n)-[r]->(m)
        RETURN id(n) as node_id, labels(n) as source_labels, properties(n) as source_props,
            id(m) as target_id, labels(m) as target_labels, properties(m) as target_props,
            type(r) as relationship_type, properties(r) as rel_props
        """

    else:
        query = f"""
        MATCH (n:{appliedFilter})-[r]->(m)
        RETURN id(n) as node_id, labels(n) as source_labels, properties(n) as source_props,
        id(m) as target_id, labels(m) as target_labels, properties(m) as target_props,
        type(r) as relationship_type, properties(r) as rel_props
        """


    result = tx.run(query)
    return list(result)

@app.route('/dataneo')
def getting_data():

    appliedFilter = request.args.get('filter',None)
    if appliedFilter is None:
        appliedFilter = ""

    with driver.session() as session:
        data = session.execute_read(fetch_data,appliedFilter)
        
    nodes = []
    links = []
    node_set = set()

    for record in data:
        node_id = record["node_id"]
        target_id = record["target_id"]
        source_labels = record["source_labels"]
        source_props = record["source_props"]
        target_labels = record["target_labels"]
        target_props = record["target_props"]
        relationship_type = record["relationship_type"]
        rel_props = record["rel_props"]

        # Create source node
        if node_id not in node_set:
            nodes.append({
                "id": node_id,
                "label": source_labels[0] if source_labels else "Unknown",  # Fallback label
                **source_props
            })
            node_set.add(node_id)

        # Create target node
        if target_id not in node_set:
            nodes.append({
                "id": target_id,
                "label": target_labels[0] if target_labels else "Unknown",  # Fallback label
                **target_props
            })
            node_set.add(target_id)

        # Create links
        links.append({
            "source": node_id,
            "target": target_id,
            "type": relationship_type,
            **rel_props
        })

    return jsonify({"nodes": nodes, "links": links})

@app.route('/')
def index():
    response = make_response()
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    param = request.args.get('filter',None)

    return render_template('index.html',filterValue=param)



if __name__ == '__main__':
    app.run(port=5001, debug=True)  # Change port if needed
