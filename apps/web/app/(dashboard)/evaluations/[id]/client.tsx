"use client";

import { motion } from "framer-motion";
import { ArrowLeft, CheckCircle, BarChart2, Activity, Target } from "lucide-react";
import Link from "next/link";
import { use } from "react";

export default function EvaluationDetail({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  
  return (
    <div className="space-y-6">
      <Link 
        href="/evaluations" 
        className="inline-flex items-center space-x-2 text-white/50 hover:text-white transition-colors text-sm"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to Evaluations</span>
      </Link>

      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-3xl font-bold text-white/90">Llama 3 Instruct - Financial Reasoning</h1>
            <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-sm border border-green-500/20 flex items-center space-x-1">
              <CheckCircle className="w-4 h-4" />
              <span>Passed</span>
            </span>
          </div>
          <p className="text-white/50 mt-2">Run ID: {resolvedParams.id} • Dataset: finance-qa-v1.2</p>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: "Overall Accuracy", value: "94.2%", icon: Target, color: "text-green-400", bg: "bg-green-500/10" },
          { label: "F1 Score", value: "0.92", icon: BarChart2, color: "text-blue-400", bg: "bg-blue-500/10" },
          { label: "Avg Latency", value: "245ms", icon: Activity, color: "text-purple-400", bg: "bg-purple-500/10" },
        ].map((metric, i) => (
          <motion.div
            key={metric.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="p-6 rounded-2xl bg-white/[0.02] border border-white/[0.05]"
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-white/50">{metric.label}</span>
              <div className={`p-2 rounded-lg ${metric.bg}`}>
                <metric.icon className={`w-5 h-5 ${metric.color}`} />
              </div>
            </div>
            <div className="text-3xl font-bold text-white/90">{metric.value}</div>
          </motion.div>
        ))}
      </div>

      {/* Detailed Results Area */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="p-6 rounded-2xl bg-white/[0.02] border border-white/[0.05] min-h-[300px]"
      >
        <h3 className="text-lg font-semibold text-white/90 mb-4">Category Breakdown</h3>
        <div className="space-y-4">
          {[
            { name: "Numerical Extraction", score: 98, color: "bg-green-400" },
            { name: "Trend Analysis", score: 85, color: "bg-yellow-400" },
            { name: "Sentiment Classification", score: 92, color: "bg-green-400" },
          ].map(cat => (
            <div key={cat.name} className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-white/70">{cat.name}</span>
                <span className="text-white/90 font-medium">{cat.score}%</span>
              </div>
              <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden">
                <div 
                  className={`h-full ${cat.color} rounded-full`}
                  style={{ width: `${cat.score}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
// export function generateStaticParams() { return [{ id: 'default' }]; }
