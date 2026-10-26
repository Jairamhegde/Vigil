import { Component } from "react";
import { Empty, Panel } from "./ui";

// Keeps one failing page from blanking the whole dashboard.
export default class ErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error, info) {
        console.error("Dashboard page crashed:", error, info.componentStack);
    }

    render() {
        if (this.state.error) {
            return (
                <Panel title="Something went wrong on this page">
                    <Empty>
                        {this.state.error.message}
                        <div style={{ marginTop: 16 }}>
                            <button className="btn" onClick={() => this.setState({ error: null })}>Try again</button>
                        </div>
                    </Empty>
                </Panel>
            );
        }

        return this.props.children;
    }
}
