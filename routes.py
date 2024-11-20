from flask import jsonify
from neo4j import GraphDatabase

# Initialize the Neo4j driver
uri = "bolt://localhost:7687"  # Change to your Neo4j instance
username = "neo4j"
password = "1234567890"
driver = GraphDatabase.driver(uri, auth=(username, password))

# Function to fetch graph data from Neo4j
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
                'node1': record['n'],
                'relationship': record['r'],
                'node2': record['m']
            })
        return data

# Define the routes for your Flask app
def configure_routes(app):
    @app.route('/graph_data', methods=['GET'])
    def get_graph():
        graph_data = fetch_graph_data()
        return jsonify(graph_data)
    
    # You can add more routes here as needed
    @app.route('/')
    def index():
        return "Welcome to the Neo4j Graph API!"
